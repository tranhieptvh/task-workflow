#!/usr/bin/env python3
"""Security gate of the task workflow plugin: keeps secrets out of the model's context.

  gate.py hook pre|post                 Claude Code hook (hook JSON on stdin), registered in hooks/hooks.json
  gate.py scan-run [--save F] -- CMD    run CMD; print (and save to F) its output only if no secret is found, else seal it
  gate.py scan PATH|- ...               exit 1 and list rule + location (never the value) when a secret is found
  gate.py scan-diff REPO                scan lines added since HEAD (plus untracked files) in a git repo
  gate.py classify [--readonly] -- CMD  print allow | confirm | deny (+ rule) for CMD, as the hook would decide

Threat model: stops ACCIDENTAL exposure (reading .env, printing a Lambda's environment, a token
pasted into a ticket). It is not a sandbox against a model that deliberately obfuscates commands.
"""
import fnmatch
import glob as globlib
import json
import os
import re
import shlex
import subprocess
import sys
import time

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATE = os.path.join(PLUGIN_ROOT, "security", "gate.py")
HOME = os.path.expanduser("~")
# Used when no task is active. Sealed dirs are always named ".sealed" so "**/.sealed/*" blocks them wherever they live.
STATE_DIR = os.environ.get("TASK_GATE_STATE_DIR") or os.path.join(HOME, ".claude", "task-security")
GLOBAL_LOG = os.path.join(STATE_DIR, "security.log")
GLOBAL_SEALED = os.path.join(STATE_DIR, ".sealed")
READ_ONLY_CMDS = {"cat", "head", "tail", "less", "more", "grep", "rg", "wc", "ls", "stat", "file", "diff", "jq"}
SAMPLE_SECRET_NAMES = [".env", ".env.local", ".envrc", "id_rsa", "server.pem", "tls.key", ".npmrc", "credentials"]
SEPARATORS = {"&&", "||", ";", "|", "&", "|&", ";;"}


# ---------------------------------------------------------------- workspace / policy

def find_workspace(cwd):
    """Nearest ancestor holding the workflow config or tasks/.current; else cwd."""
    start = os.path.abspath(cwd or os.getcwd())
    d = start
    while True:
        if os.path.isfile(os.path.join(d, ".claude", "task-workflow.yml")) or \
           os.path.isfile(os.path.join(d, "tasks", ".current")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return start
        d = parent


def tasks_dir(ws):
    try:
        with open(os.path.join(ws, ".claude", "task-workflow.yml"), encoding="utf-8") as f:
            m = re.search(r"(?m)^tasks_dir:\s*['\"]?([^'\"\s#]+)", f.read())
            if m:
                return os.path.join(ws, m.group(1))
    except OSError:
        pass
    return os.path.join(ws, "tasks")


def active_task(ws):
    td = tasks_dir(ws)
    try:
        with open(os.path.join(td, ".current"), encoding="utf-8") as f:
            tid = f.read().strip()
    except OSError:
        return None
    path = os.path.join(td, tid)
    return path if tid and os.path.isdir(path) else None


def load_policy(ws):
    with open(os.path.join(PLUGIN_ROOT, "security", "policy.default.json"), encoding="utf-8") as f:
        p = json.load(f)
    p["project_cmds"] = {"allow": [], "confirm": [], "deny": []}
    proj = os.path.join(ws, ".claude", "task-security.json")
    if os.path.isfile(proj):
        with open(proj, encoding="utf-8") as f:
            o = json.load(f)  # malformed project policy -> exception -> fail-closed
        # Projects may only ADD restrictions.
        p["secret_paths"] += [str(x) for x in o.get("secret_paths", [])]
        for x in o.get("secret_patterns", []):
            entry = x if isinstance(x, dict) else {"regex": str(x)}
            p["secret_patterns"].append({"id": "project:" + str(entry.get("id", "pattern")), "regex": str(entry["regex"])})
        cmds = o.get("commands", {})
        for k in p["project_cmds"]:
            p["project_cmds"][k] = [str(x) for x in cmds.get(k, [])]
    p["_patterns"] = [(x["id"], re.compile(x["regex"])) for x in p["secret_patterns"]]
    return p


# ---------------------------------------------------------------- matching helpers

def _expand(path, cwd):
    path = path.strip().strip("'\"").replace("${HOME}", HOME).replace("$HOME", HOME)
    return os.path.normpath(os.path.join(cwd, os.path.expanduser(path)))


def _glob_match(abs_path, pattern):
    pattern = pattern.replace("{plugin}", PLUGIN_ROOT)
    if pattern.startswith("~/"):
        pattern = HOME + pattern[1:]
    if pattern.startswith("**/"):
        rest = pattern[3:]
        if "/" not in rest:
            return fnmatch.fnmatchcase(os.path.basename(abs_path), rest)
        return fnmatch.fnmatchcase(abs_path, "*/" + rest)
    if pattern.startswith("/"):
        return fnmatch.fnmatchcase(abs_path, pattern)
    return fnmatch.fnmatchcase(abs_path, "*/" + pattern)


def is_secret_path(p, path, cwd):
    a = _expand(path, cwd)
    if any(fnmatch.fnmatchcase(os.path.basename(a), e) for e in p["secret_path_exceptions"]):
        return False
    return any(_glob_match(a, g) for g in p["secret_paths"])


def is_protected_path(p, path, cwd):
    a = _expand(path, cwd)
    return any(_glob_match(a, g) for g in p["protected_paths"])


def _under(path, root):
    path, root = os.path.realpath(path), os.path.realpath(root)
    return path == root or path.startswith(root + os.sep)


def scan_text(p, text):
    """[(rule_id, line_no)] for every secret-like match. Never returns the value."""
    hits = set()
    for rid, rx in p["_patterns"]:
        for m in rx.finditer(text):
            hits.add((rid, text.count("\n", 0, m.start()) + 1))
    return sorted(hits, key=lambda h: (h[1], h[0]))


def mask(p, text):
    for rid, rx in p["_patterns"]:
        text = rx.sub("[REDACTED:%s]" % rid, text)
    return text


# ---------------------------------------------------------------- logging / sealing

def log_event(ws, event, **fields):
    task = active_task(ws) if ws else None
    path = os.path.join(task, ".security.log") if task else GLOBAL_LOG
    entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "event": event}
    entry.update(fields)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass  # logging must never break the gate


def seal(ws, text, label):
    task = active_task(ws) if ws else None
    d = os.path.join(task, "evidence", ".sealed") if task else GLOBAL_SEALED
    os.makedirs(d, mode=0o700, exist_ok=True)
    path = os.path.join(d, "%s-%s.txt" % (time.strftime("%Y%m%d-%H%M%S"), re.sub(r"[^\w.-]+", "_", label)[:60]))
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def sealed_notice(hits, path):
    rules = sorted({r for r, _ in hits})
    lines = sorted({ln for _, ln in hits})
    return ("[security gate] Output withheld: %d secret-like match(es) (%s) at line(s) %s. "
            "The original was saved for the user at %s (the model cannot read it). "
            "Narrow the command (e.g. --query / field selection) so secrets are not in the output."
            % (len(hits), ", ".join(rules), ", ".join(map(str, lines[:20])), path))


# ---------------------------------------------------------------- bash parsing

def _tokens(cmd):
    try:
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        return list(lex)
    except ValueError:
        # Unparseable (e.g. heredoc with an apostrophe): fall back to a coarser split; checks still run.
        return [t for t in re.split(r"\s+", cmd) if t]


def segments(cmd):
    segs = []
    for line in cmd.splitlines() or [cmd]:
        cur = []
        for t in _tokens(line):
            if t in SEPARATORS or (t and set(t) <= set(";&|")):
                if cur:
                    segs.append(cur)
                cur = []
            else:
                cur.append(t)
        if cur:
            segs.append(cur)
    return segs


def path_fragments(cmd):
    frags = set()
    for t in _tokens(cmd):
        for f in re.split(r"[\s'\"()=,;|&<>`]+", t):
            if f:
                frags.add(f)
    return frags


def existing_paths(frag, cwd):
    """Paths on disk a fragment refers to (directly or as a shell glob)."""
    a = _expand(frag, cwd)
    if any(c in frag for c in "*?["):
        return globlib.glob(a, include_hidden=True)[:200] if sys.version_info >= (3, 11) else globlib.glob(a)[:200]
    return [a] if os.path.lexists(a) else []


WRITE_CMDS = {"cp", "mv", "rm", "tee", "ln", "chmod", "chown", "truncate", "dd", "install", "rsync", "touch", "patch"}
IN_PLACE_CMDS = {"sed", "perl"}  # write only with -i / --in-place
INLINE_FLAGS = {"python": "-c", "python3": "-c", "node": "-e", "ruby": "-e", "perl": "-e", "bash": "-c", "sh": "-c", "zsh": "-c"}


def _cmd_index(seg):
    """Index of the command word, skipping VAR=value assignments."""
    i = 0
    while i < len(seg) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", seg[i]):
        i += 1
    return i


def protected_write_targets(segs, cwd):
    """Paths a command may WRITE: redirect targets, arguments of write commands, paths named inside inline or stdin
    scripts (python3 - <<EOF ...). Relative paths resolve against the session cwd and every `cd` target in the command.
    Running a protected script (python3 gate.py ...) is not a write."""
    targets, bases, stdin_script = [], [cwd], False

    def add(f):
        for b in bases:
            targets.extend(existing_paths(f, b) or [_expand(f, b)])

    for seg in segs:
        ci = _cmd_index(seg)
        if ci + 1 < len(seg) and seg[ci] == "cd":
            bases.append(_expand(seg[ci + 1], cwd))
        for i, t in enumerate(seg):
            if t in (">", ">>", ">|", "&>", "&>>") and i + 1 < len(seg):
                add(seg[i + 1])
        if ci >= len(seg):
            continue
        name = os.path.basename(seg[ci])
        in_place = name in IN_PLACE_CMDS and any(t.startswith("-i") or t == "--in-place" for t in seg[ci + 1:])
        if name in INLINE_FLAGS:
            args = [t for t in seg[ci + 1:] if t == "-" or not t.startswith("-")]
            stdin_script = stdin_script or (bool(args) and args[0] in ("-", "<<", "<<-", "<<<", "<")) \
                or (name in ("bash", "sh", "zsh") and "-s" in seg[ci + 1:])
        if stdin_script:
            words = seg  # heredoc body lines arrive as segments of their own
        elif name in WRITE_CMDS or in_place or (name in INLINE_FLAGS and INLINE_FLAGS[name] in seg[ci + 1:]):
            words = seg[ci + 1:]
        else:
            continue
        for t in words:
            for f in re.split(r"[\s'\"()=,;|&<>`]+", t):
                if f and not f.startswith("-"):
                    add(f)
    return targets


def get_query(tokens):
    for i, t in enumerate(tokens):
        if t == "--query" and i + 1 < len(tokens):
            return tokens[i + 1]
        if t.startswith("--query="):
            return t.split("=", 1)[1]
    return None


def unwrap_gate(seg):
    """For `python3 .../gate.py scan-run [--save F] -- CMD` return ('scan-run', CMD, F);
    for the read-only gate modes (scan, scan-diff, classify) return ('scan', None, None)."""
    if len(seg) >= 3 and os.path.basename(seg[0]).startswith("python") and seg[1].endswith(os.path.join("security", "gate.py")):
        mode = seg[2]
        if mode == "scan-run":
            rest, save = seg[3:], None
            if "--" in rest:
                opts, rest = rest[:rest.index("--")], rest[rest.index("--") + 1:]
                if "--save" in opts and opts.index("--save") + 1 < len(opts):
                    save = opts[opts.index("--save") + 1]
            inner = (rest[0] if len(rest) == 1 else shlex.join(rest)) if rest else ""
            return "scan-run", inner, save
        if mode in ("scan", "scan-diff", "classify"):
            return "scan", None, None
    return None, None, None


# ---------------------------------------------------------------- decisions

# git global options sit between "git" and the subcommand (git -C repo show); drop them so rules see "git show"
_GIT_ARG = r"(?:'[^']*'|\"[^\"]*\"|\S+)"
GIT_GLOBAL = re.compile(r"\bgit((?:\s+(?:-[Cc]\s+%s|--(?:git-dir|work-tree|namespace)(?:=|\s+)%s|--no-pager|-P|--bare|--no-replace-objects|--literal-pathspecs))+)(?=\s)" % (_GIT_ARG, _GIT_ARG))


def norm_git(s):
    return GIT_GLOBAL.sub("git", s)


def _names_only(line):
    """True if a scan-required command prints only names, stats or counts - no file content."""
    if re.search(r"\s(?:-p|-u|--patch)\b", line):
        return False
    if re.search(r"--(?:stat|name-only|name-status|shortstat|numstat|quiet|exit-code|summary)\b", line):
        return True
    # git grep -c / -l / -L / -q: counts or file names only
    return bool(re.search(r"\bgit\s+grep\b", line)
                and re.search(r"\s(?:-[a-zA-Z]*[clLq][a-zA-Z]*|--count|--files-with-matches|--files-without-match)\b", line))


def check_safe_form(p, cmd, tokens, scanned):
    for rule in p["safe_form"]:
        if not re.search(rule["regex"], cmd):
            continue
        q = get_query(tokens)
        rid = rule["id"]
        if rid == "aws-lambda-config":
            ok = q is not None and "Environment" not in q.replace("keys(Environment.Variables)", "")
        elif rid == "aws-appsync-keys":
            ok = q is not None and "{" in q and not re.search(r"\bid\b", q)
        elif rid == "aws-ssm-param":
            ok = q is not None and "Value" not in q
        elif rid == "scan-required":
            # judged per command, so one names-only command cannot clear another that prints content
            ok = scanned or all(_names_only(l) for l in cmd.splitlines() if re.search(rule["regex"], l))
        else:
            ok = False
        if not ok:
            return ("deny", rid, rule["hint"].replace("{gate}", GATE))
    return None


def _glob_rx(g):
    return re.compile(fnmatch.translate(g))


def classify_readonly(p, seg, task_dir, cwd):
    s = norm_git(" ".join(seg))
    # housekeeping inside the task folder (e.g. removing the .readonly marker) is not a state change
    if seg and seg[0] in ("rm", "mv", "rmdir", "mkdir", "touch"):
        args = [t for t in seg[1:] if not t.startswith("-")]
        if args and all(_under(_expand(t, cwd), task_dir) for t in args):
            return "allow"
    if any(re.search(r, s) for r in p["readonly"]["deny"]) or any(_glob_rx(g).match(s) for g in p["project_cmds"]["deny"]):
        return "deny"
    for i, t in enumerate(seg):
        if t in (">", ">>", ">|", "&>", "&>>") and i + 1 < len(seg):
            target = seg[i + 1]
            if target != "/dev/null" and not _under(_expand(target, cwd), task_dir):
                return "deny"
    if any(re.search(r, s) for r in p["readonly"]["confirm"]) or any(_glob_rx(g).match(s) for g in p["project_cmds"]["confirm"]):
        return "ask"
    if any(re.search(r, s) for r in p["readonly"]["allow"]) or any(_glob_rx(g).match(s) for g in p["project_cmds"]["allow"]):
        return "allow"
    return "ask"


def check_bash(p, cmd, cwd, ws, readonly_task=None, scanned=False):
    for rule in p["always_deny"]:
        if re.search(rule["regex"], cmd):
            return ("deny", rule["id"], rule["reason"])

    segs = segments(cmd)
    plain = []
    for seg in segs:
        mode, inner, save = unwrap_gate(seg)
        if mode == "scan-run":
            if not inner:
                return ("deny", "scan-run-usage", "usage: python3 %s scan-run [--save FILE] -- '<command>'" % GATE)
            if save and readonly_task and not _under(_expand(save, cwd), readonly_task):
                return ("deny", "readonly", "read-only investigation: --save must point inside the task folder")
            d = check_bash(p, inner, cwd, ws, readonly_task, scanned=True)
            if d and d[0] != "allow":
                return d
        elif mode != "scan":
            plain.append(seg)
    if not plain:
        return None
    rest = norm_git("\n".join(shlex.join(s) for s in plain))
    tokens = [t for s in plain for t in s]

    d = check_safe_form(p, rest, tokens, scanned)
    if d:
        return d

    frags = path_fragments(rest)
    for f in frags:
        for a in existing_paths(f, cwd):
            if is_secret_path(p, a, cwd):
                return ("deny", "secret-path", "command touches a secret file (%s); read only the non-secret fields you need, or ask the user" % os.path.basename(a))
    for target in protected_write_targets(plain, cwd):
        if is_protected_path(p, target, cwd):
            return ("deny", "protected-path", "%s is protected by the security gate; ask the user to change it by hand" % target)

    if readonly_task:
        decisions = [classify_readonly(p, s, readonly_task, cwd) for s in plain]
        if "deny" in decisions:
            return ("deny", "readonly", "read-only investigation: this command may change state. If a change is really needed, create a separate task (/task:new <id>-fix --from <task>)")
        if "ask" in decisions:
            return ("ask", "readonly-confirm", "read-only investigation: this command reads business/personal data or is not classified. Confirm the command, env/profile and reason")
    return None


def check_pre(p, data, cwd, ws):
    tool = data.get("tool_name", "")
    ti = data.get("tool_input", {}) or {}
    task = active_task(ws)
    ro = task if task and os.path.isfile(os.path.join(task, ".readonly")) else None

    if tool == "Bash":
        return check_bash(p, str(ti.get("command", "")), cwd, ws, ro)

    path = ti.get("file_path") or ti.get("notebook_path")
    if tool == "Read" and path and is_secret_path(p, path, cwd):
        return ("deny", "secret-path", "%s is a secret file and cannot be read" % os.path.basename(path))
    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit") and path:
        if is_secret_path(p, path, cwd):
            return ("deny", "secret-path", "%s is a secret file; the user must edit it by hand" % os.path.basename(path))
        if is_protected_path(p, path, cwd):
            return ("deny", "protected-path", "%s is protected by the security gate; ask the user to change it by hand" % path)
        if ro and not _under(_expand(path, cwd), ro):
            return ("deny", "readonly", "read-only investigation: only files inside the task folder may be written")
    if tool == "Grep":
        target = ti.get("path") or cwd
        if is_secret_path(p, target, cwd):
            return ("deny", "secret-path", "%s is a secret file and cannot be searched" % os.path.basename(target))
        if ti.get("output_mode") == "content" and os.path.isdir(_expand(target, cwd)):
            g, typ = ti.get("glob"), ti.get("type")
            if not g and not typ:
                return ("deny", "grep-unscoped", "content search over a directory can print secret files (.env.local, keys...). Add a 'type' (e.g. js) or a 'glob' (e.g. *.ts)")
            if g and any(fnmatch.fnmatchcase(n, g.split("/")[-1]) for n in SAMPLE_SECRET_NAMES):
                return ("deny", "grep-unscoped", "glob '%s' also matches secret files; use a narrower glob or a 'type'" % g)
    return None


def check_post(p, data, ws):
    tool = data.get("tool_name", "")
    if not tool.startswith("mcp__"):
        return None
    resp = data.get("tool_response", "")
    text = resp if isinstance(resp, str) else json.dumps(resp, ensure_ascii=False)
    hits = scan_text(p, text)
    if not hits:
        return None
    path = seal(ws, text, tool)
    log_event(ws, "seal", tool=tool, rules=sorted({r for r, _ in hits}), sealed=path)
    return sealed_notice(hits, path)


# ---------------------------------------------------------------- entry points

def hook(mode):
    raw = sys.stdin.read()
    if os.environ.get("TASK_SECURITY_GATE") == "off":
        return 0
    ws = None
    try:
        data = json.loads(raw)
        cwd = data.get("cwd") or os.getcwd()
        ws = find_workspace(cwd)
        p = load_policy(ws)
        if mode == "post":
            notice = check_post(p, data, ws)
            if notice:
                print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "updatedMCPToolOutput": notice}}))
            return 0
        decision = check_pre(p, data, cwd, ws)
        if decision:
            what = data.get("tool_input", {}).get("command") or data.get("tool_input", {}).get("file_path") or data.get("tool_input", {}).get("path") or ""
            log_event(ws, decision[0], tool=data.get("tool_name"), rule=decision[1], target=mask(p, str(what))[:300])
    except Exception as e:  # fail-closed
        if mode == "post":
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                                     "updatedMCPToolOutput": "[security gate] output withheld: gate error (%s)" % type(e).__name__}}))
            return 0
        decision = ("deny", "gate-error", "security gate error (%s: %s). Fix the cause, or the user can start Claude Code with the gate disabled" % (type(e).__name__, e))
        log_event(ws, "deny", rule="gate-error", error=str(e)[:300])
    if decision and decision[0] in ("deny", "ask"):
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision[0],
                                                 "permissionDecisionReason": "[security gate] %s: %s" % (decision[1], decision[2])}}))
    return 0


def scan_run(argv):
    save = None
    if "--" in argv:
        opts, argv = argv[:argv.index("--")], argv[argv.index("--") + 1:]
        if "--save" in opts and opts.index("--save") + 1 < len(opts):
            save = opts[opts.index("--save") + 1]
    if not argv:
        print("usage: gate.py scan-run [--save FILE] -- '<command>'", file=sys.stderr)
        return 2
    cmd = argv[0] if len(argv) == 1 else shlex.join(argv)
    proc = subprocess.run(["bash", "-c", cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = proc.stdout.decode("utf-8", "replace")
    ws = find_workspace(os.getcwd())
    p = load_policy(ws)
    hits = scan_text(p, out)
    if hits:
        path = seal(ws, out, "scan-run")
        log_event(ws, "seal", tool="scan-run", rules=sorted({r for r, _ in hits}), target=mask(p, cmd)[:300], sealed=path)
        notice = sealed_notice(hits, path)
        print(notice)
        out = notice + "\n"
    else:
        sys.stdout.write(out)
    if save:
        os.makedirs(os.path.dirname(os.path.abspath(save)), exist_ok=True)
        with open(save, "w", encoding="utf-8") as f:
            f.write("$ %s\n%s" % (mask(p, cmd), out))
    return proc.returncode


def classify(argv):
    readonly = "--readonly" in argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    cmd = argv[0] if len(argv) == 1 else shlex.join(argv)
    cwd = os.getcwd()
    ws = find_workspace(cwd)
    p = load_policy(ws)
    ro = (active_task(ws) or os.path.join(tasks_dir(ws), "_")) if readonly else None
    d = check_bash(p, cmd, cwd, ws, ro)
    level = {"deny": "deny", "ask": "confirm"}.get(d[0], "allow") if d else "allow"
    print(level if not d else "%s  %s: %s" % (level, d[1], d[2]))
    return 0


def _scan_file(p, path, found, label=None):
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        print("skip  %s (%s)" % (path, e.strerror))
        return
    if b"\0" in data[:8192]:
        print("skip  %s (binary, not scannable)" % path)
        return
    for rid, ln in scan_text(p, data.decode("utf-8", "replace")):
        found.append((rid, "%s:%d" % (label or path, ln)))


def scan_paths(argv):
    ws = find_workspace(os.getcwd())
    p = load_policy(ws)
    found = []
    for path in argv:
        if path == "-":
            for rid, ln in scan_text(p, sys.stdin.read()):
                found.append((rid, "stdin:%d" % ln))
        elif os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if d not in (".git", "node_modules", ".sealed")]
                for name in files:
                    _scan_file(p, os.path.join(root, name), found)
        else:
            _scan_file(p, path, found)
    return _report(found)


def scan_diff(argv):
    repo = argv[0] if argv else "."
    ws = find_workspace(os.getcwd())
    p = load_policy(ws)
    found = []
    head = subprocess.run(["git", "-C", repo, "rev-parse", "--verify", "-q", "HEAD"], capture_output=True)
    base = ["HEAD"] if head.returncode == 0 else ["--cached"]
    diff = subprocess.run(["git", "-C", repo, "diff", "--no-color", "-U0"] + base, capture_output=True, text=True, errors="replace").stdout
    current, line_no = None, 0
    for line in diff.splitlines():
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else line[4:]
        elif line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            line_no = int(m.group(1)) if m else 0
        elif line.startswith("+"):
            for rid, _ in scan_text(p, line[1:]):
                found.append((rid, "%s:%d" % (current, line_no)))
            line_no += 1
    untracked = subprocess.run(["git", "-C", repo, "ls-files", "--others", "--exclude-standard"], capture_output=True, text=True).stdout.split("\n")
    for rel in filter(None, untracked):
        if is_secret_path(p, os.path.join(repo, rel), os.getcwd()):
            # not part of the change and never opened; flag the commit risk only
            print("warn    secret-file-untracked %s (not in .gitignore; would be committed by 'git add .')" % rel)
            continue
        _scan_file(p, os.path.join(repo, rel), found, label=rel)
    return _report(found)


def _report(found):
    for rid, where in found:
        print("secret  %-20s %s" % (rid, where))
    print("result: %s" % ("%d secret-like match(es)" % len(found) if found else "clean"))
    return 1 if found else 0


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "hook" and rest and rest[0] in ("pre", "post"):
        return hook(rest[0])
    if cmd == "scan-run":
        return scan_run(rest)
    if cmd == "scan":
        return scan_paths(rest or ["-"])
    if cmd == "scan-diff":
        return scan_diff(rest)
    if cmd == "classify":
        return classify(rest)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
