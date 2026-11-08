#!/usr/bin/env python3
"""Self-check of the security gate. Must pass before every plugin commit:  python3 security/test_gate.py

Fake secrets are assembled at runtime so this file never contains a secret-like literal itself.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# keep the test run's log and sealed files out of the real ~/.claude/task-security
_STATE = tempfile.TemporaryDirectory()
os.environ["TASK_GATE_STATE_DIR"] = _STATE.name
import gate  # noqa: E402

GATE = os.path.join(HERE, "gate.py")
J = "".join
FAKE = {
    "aws-access-key-id": J(["AK", "IA", "ABCDEFGHIJKLMNOP"]),
    "aws-secret-json": J(['"Secret', 'AccessKey": "', "wJalrXUtnFEMIK7MDENGbPxRfiCY", '"']),
    "private-key": J(["-----BEGIN RSA ", "PRIVATE KEY-----"]),
    "jwt": J(["ey", "JhbGciOiJIUzI1NiJ9.", "ey", "JzdWIiOiIxMjM0NTY3ODkwIn0.", "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"]),
    "appsync-api-key": J(["da", "2-", "abcdefghijklmnopqrstuvwxyz"]),
    "github-token": J(["gh", "p_", "A" * 36]),
    "slack-token": J(["xo", "xb-", "1234567890-abcdefghij"]),
    "connection-string": J(["postgres", "://admin:", "s3cretpass@db.local/app"]),
    "secret-literal": J(["api_", 'key = "', "Zx9-very-real-value", '"']),
    "dotenv-secret": J(["DB_PASS", "WORD=", "hunter2hunter2"]),
}
BENIGN = [
    "password = form.password",
    "const token = getToken();",
    "API_KEY=${API_KEY}",
    "api_key = '<YOUR_API_KEY>'",
    "secret: process.env.SECRET",
    "the AROAEXAMPLEROLEID12 role id",
    "git commit -m 'fix token refresh'",
    "SAMPLE_SECRET_NAMES = ['.env', '.env.local', 'id_rsa']",
    "API_TOKEN = getToken(request)",
    "export GITHUB_TOKEN=$(gh auth token)",
]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = os.path.realpath(self.tmp.name)
        os.makedirs(os.path.join(self.ws, ".claude"))
        with open(os.path.join(self.ws, ".claude", "task-workflow.yml"), "w") as f:
            f.write("tasks_dir: tasks\n")
        os.makedirs(os.path.join(self.ws, "sub"))
        for rel in (".env", "sub/.env.local", ".env.example", "app.js"):
            with open(os.path.join(self.ws, rel), "w") as f:
                f.write("x\n")
        self.p = gate.load_policy(self.ws)

    def tearDown(self):
        self.tmp.cleanup()

    def bash(self, cmd, ro=None):
        return gate.check_bash(self.p, cmd, self.ws, self.ws, ro)

    def pre(self, tool, **ti):
        return gate.check_pre(self.p, {"tool_name": tool, "tool_input": ti, "cwd": self.ws}, self.ws, self.ws)

    def assertDecision(self, d, expected):
        got = d[0] if d else "allow"
        self.assertEqual(got, expected, d)


class TestScanner(Base):
    def test_detects_every_fake_secret(self):
        for rid, value in FAKE.items():
            hits = gate.scan_text(self.p, "line one\n" + value + "\n")
            self.assertIn(rid, {r for r, _ in hits}, "%s not detected" % rid)
            self.assertIn(2, {ln for _, ln in hits})

    def test_ignores_benign_text(self):
        for text in BENIGN:
            self.assertEqual(gate.scan_text(self.p, text), [], text)

    def test_mask_removes_values(self):
        for value in FAKE.values():
            self.assertNotIn(value, gate.mask(self.p, "x\n" + value + "\ny"))


class TestPaths(Base):
    def test_secret_paths(self):
        for path in (".env", "sub/.env.local", "~/.aws/credentials", "~/.ssh/id_ed25519", "~/.claude.json",
                     "tasks/T/evidence/.sealed/a.txt", "/tmp/elsewhere/.sealed/b.txt", "certs/server.pem", ".npmrc"):
            self.assertTrue(gate.is_secret_path(self.p, path, self.ws), path)

    def test_non_secret_paths(self):
        for path in (".env.example", "app.js", "src/credentials_helper.js", "~/.ssh/id_ed25519.pub", "README.md"):
            self.assertFalse(gate.is_secret_path(self.p, path, self.ws), path)


class TestBash(Base):
    def test_secret_file_access_denied(self):
        for cmd in ("cat .env", "head -3 sub/.env.local", "python3 -c \"print(open('.env').read())\"",
                    "cp .env /tmp/x", "grep KEY .en*"):
            self.assertDecision(self.bash(cmd), "deny")

    def test_env_printing_denied(self):
        for cmd in ("env", "printenv", "printenv AWS_SECRET_ACCESS_KEY", "env | grep AWS", "ls; set", "export -p",
                    "aws configure get aws_secret_access_key --profile x", "aws configure export-credentials",
                    "aws secretsmanager get-secret-value --secret-id x",
                    "aws ssm get-parameter --name x --with-decryption",
                    "aws lambda get-function --function-name f", "aws sts assume-role --role-arn r --role-session-name s",
                    "aws ecr get-login-password", "gh auth token", "export TASK_SECURITY_GATE=off"):
            self.assertDecision(self.bash(cmd), "deny")

    def test_normal_commands_allowed(self):
        for cmd in ("ls -la", "git status", "git log --oneline -5", "cat app.js", "env FOO=1 node app.js",
                    "set -euo pipefail; ls", "export FOO=bar", "/usr/bin/env python3 -V", "cat .env.example",
                    "git diff --stat", "git show --name-only HEAD", "grep -r credentials src/",
                    "git commit -m \"it's done\"", "aws lambda list-functions --profile dev"):
            self.assertDecision(self.bash(cmd), "allow")

    def test_safe_forms(self):
        self.assertDecision(self.bash("aws lambda get-function-configuration --function-name f"), "deny")
        self.assertDecision(self.bash("aws lambda get-function-configuration --function-name f --query 'Environment.Variables'"), "deny")
        self.assertDecision(self.bash("aws lambda get-function-configuration --function-name f --query '{R:Runtime,EnvKeys:keys(Environment.Variables)}'"), "allow")
        self.assertDecision(self.bash("aws appsync list-api-keys --api-id a"), "deny")
        self.assertDecision(self.bash("aws appsync list-api-keys --api-id a --query 'apiKeys[].{id:id,expires:expires}'"), "deny")
        self.assertDecision(self.bash("aws appsync list-api-keys --api-id a --query 'apiKeys[].{expires:expires,description:description}'"), "allow")
        self.assertDecision(self.bash("aws ssm get-parameter --name x"), "deny")
        self.assertDecision(self.bash("aws ssm get-parameter --name x --query 'Parameter.{Name:Name,Version:Version}'"), "allow")
        self.assertDecision(self.bash("git show HEAD"), "deny")
        self.assertDecision(self.bash("git log -p -- src/a.js"), "deny")
        self.assertDecision(self.bash("aws logs filter-log-events --log-group-name g"), "deny")
        self.assertDecision(self.bash("python3 %s scan-run -- 'git show HEAD'" % GATE), "allow")
        self.assertDecision(self.bash("python3 %s scan-run -- git log -p -- src/a.js" % GATE), "allow")
        self.assertDecision(self.bash("python3 %s scan-run -- 'cat .env'" % GATE), "deny")
        self.assertDecision(self.bash("python3 %s scan-run -- 'printenv'" % GATE), "deny")

    def test_git_content_commands(self):
        for cmd in ("git -C sub show HEAD", "git -C sub log -p -1", "git --no-pager -C sub show HEAD:app.js",
                    "git grep -n token HEAD", "git -C sub grep token origin/main", "git cat-file -p HEAD:app.js",
                    "git -c core.pager=cat show HEAD", "git diff --stat; git show HEAD"):
            self.assertDecision(self.bash(cmd), "deny")
        for cmd in ("git -C sub grep -c brotli origin/main", "git grep -l token", "git -C sub grep --count x HEAD",
                    "git -C sub ls-tree -r --name-only HEAD", "git -C sub show --stat HEAD", "git log --grep=fix --oneline",
                    "python3 %s scan-run -- 'git -C sub grep -n x HEAD'" % GATE):
            self.assertDecision(self.bash(cmd), "allow")

    def test_protected_writes_via_cd_and_stdin(self):
        sec = os.path.dirname(GATE)
        self.assertDecision(self.bash("cd %s && echo x > gate.py" % sec), "deny")
        self.assertDecision(self.bash("cd %s && python3 - <<'EOF'\nopen('policy.default.json', 'w')\nEOF" % sec), "deny")
        self.assertDecision(self.bash("bash -s <<'EOF'\necho x > %s\nEOF" % GATE), "deny")
        self.assertDecision(self.bash("python3 - <<'EOF'\nprint(1)\nEOF"), "allow")
        self.assertDecision(self.bash("cd %s && cat gate.py" % sec), "allow")

    def test_protected_paths(self):
        with open(os.path.join(self.ws, ".claude", "settings.json"), "w") as f:
            f.write("{}")
        self.assertDecision(self.bash("echo '{}' > .claude/settings.json"), "deny")
        self.assertDecision(self.bash("sed -i '' s/a/b/ .claude/settings.json"), "deny")
        self.assertDecision(self.bash("cat .claude/settings.json"), "allow")
        self.assertDecision(self.bash("sed -n 1p .claude/settings.json"), "allow")
        self.assertDecision(self.bash("python3 -c \"open('.claude/settings.json','w').write('{}')\""), "deny")
        self.assertDecision(self.bash("cp /tmp/x %s" % GATE), "deny")
        self.assertDecision(self.bash("python3 %s classify -- 'git status'" % GATE), "allow")
        self.assertDecision(self.bash("python3 %s scan /dev/null" % GATE), "allow")
        self.assertDecision(self.pre("Edit", file_path=os.path.join(self.ws, ".claude", "settings.json")), "deny")
        self.assertDecision(self.pre("Write", file_path=GATE), "deny")


class TestReadonly(Base):
    def setUp(self):
        super().setUp()
        self.task = os.path.join(self.ws, "tasks", "T-1")
        os.makedirs(os.path.join(self.task, "evidence"))
        with open(os.path.join(self.ws, "tasks", ".current"), "w") as f:
            f.write("T-1")
        open(os.path.join(self.task, ".readonly"), "w").close()
        with open(os.path.join(self.ws, ".claude", "task-security.json"), "w") as f:
            json.dump({"commands": {"allow": ["amplify status*"], "confirm": ["amplify env checkout *"], "deny": ["make deploy*"]},
                       "secret_paths": ["e2e/.auth/*"]}, f)
        self.p = gate.load_policy(self.ws)

    def test_writes_denied(self):
        for cmd in ("aws s3 rm s3://b/k", "aws lambda update-function-code --function-name f", "git commit -m x",
                    "git push", "rm -rf build", "echo hi > out.txt", "sed -i '' s/a/b/ app.js", "npm install",
                    "amplify push", "make deploy prod", "find . -name x -delete",
                    "aws dynamodb put-item --table-name t --item {}", "aws cognito-idp admin-delete-user --user-pool-id p --username u"):
            self.assertDecision(self.bash(cmd, ro=self.task), "deny")

    def test_confirm_and_unknown_ask(self):
        for cmd in ("aws dynamodb scan --table-name t", "curl https://example.com", "node script.js",
                    "amplify env checkout dev", "terraform plan", "aws s3 cp s3://b/k ."):
            self.assertDecision(self.bash(cmd, ro=self.task), "ask")

    def test_reads_allowed(self):
        for cmd in ("ls", "git log --oneline", "aws lambda list-functions --profile dev", "aws sts get-caller-identity --profile dev",
                    "cat app.js | jq .", "amplify status", "echo hi > tasks/T-1/evidence/a.txt", "grep -n x app.js > /dev/null",
                    "aws cloudformation describe-stacks --profile dev", "aws cognito-idp admin-get-user --user-pool-id p --username u"):
            d = self.bash(cmd, ro=self.task)
            expected = "ask" if "admin-get-user" in cmd else "allow"
            self.assertDecision(d, expected)

    def test_git_global_options_in_readonly(self):
        self.assertDecision(self.bash("git -C sub push", ro=self.task), "deny")
        for cmd in ("git -C sub ls-tree -r --name-only origin/main", "git -C sub grep -c x origin/main"):
            self.assertDecision(self.bash(cmd, ro=self.task), "allow")

    def test_gate_wrapper_in_readonly(self):
        ev = os.path.join(self.task, "evidence", "Q1.txt")
        self.assertDecision(self.bash("python3 %s scan-run --save %s -- 'aws lambda list-functions --profile dev'" % (GATE, ev), ro=self.task), "allow")
        self.assertDecision(self.bash("python3 %s scan-run --save %s -- 'grep -n x app.js'" % (GATE, ev), ro=self.task), "allow")
        self.assertDecision(self.bash("python3 %s scan-run --save /tmp/out.txt -- 'ls'" % GATE, ro=self.task), "deny")
        self.assertDecision(self.bash("python3 %s scan-run --save %s -- 'git push'" % (GATE, ev), ro=self.task), "deny")
        self.assertDecision(self.bash("python3 %s classify --readonly -- 'git push'" % GATE, ro=self.task), "allow")

    def test_task_housekeeping(self):
        self.assertDecision(self.bash("rm -f %s" % os.path.join(self.task, ".readonly"), ro=self.task), "allow")
        self.assertDecision(self.bash("cd %s && rm -f .readonly" % self.task, ro=self.task), "deny")  # relative to ws cwd: outside
        self.assertDecision(self.bash("rm -rf %s" % os.path.join(self.ws, "app.js"), ro=self.task), "deny")
        self.assertDecision(self.bash("mkdir -p %s" % os.path.join(self.task, "evidence", "e2e"), ro=self.task), "allow")

    def test_file_tools(self):
        self.assertDecision(self.pre("Write", file_path=os.path.join(self.ws, "app.js")), "deny")
        self.assertDecision(self.pre("Write", file_path=os.path.join(self.task, "evidence", "Q1.txt")), "allow")
        self.assertDecision(self.pre("Read", file_path=os.path.join(self.ws, "e2e", ".auth", "dev.json")), "deny")

    def test_no_readonly_outside_marker(self):
        os.remove(os.path.join(self.task, ".readonly"))
        self.assertDecision(self.bash("git commit -m x", ro=None), "allow")
        self.assertDecision(self.pre("Write", file_path=os.path.join(self.ws, "app.js")), "allow")


class TestFileTools(Base):
    def test_read(self):
        self.assertDecision(self.pre("Read", file_path=os.path.join(self.ws, ".env")), "deny")
        self.assertDecision(self.pre("Read", file_path=os.path.join(self.ws, ".env.example")), "allow")
        self.assertDecision(self.pre("Read", file_path=os.path.join(self.ws, "app.js")), "allow")

    def test_grep(self):
        self.assertDecision(self.pre("Grep", pattern="x", path=self.ws, output_mode="content"), "deny")
        self.assertDecision(self.pre("Grep", pattern="x", path=self.ws, output_mode="content", glob="*"), "deny")
        self.assertDecision(self.pre("Grep", pattern="x", path=self.ws, output_mode="content", type="js"), "allow")
        self.assertDecision(self.pre("Grep", pattern="x", path=self.ws, output_mode="content", glob="**/*.js"), "allow")
        self.assertDecision(self.pre("Grep", pattern="x", path=self.ws), "allow")
        self.assertDecision(self.pre("Grep", pattern="x", path=os.path.join(self.ws, ".env")), "deny")


class TestEndToEnd(Base):
    def run_gate(self, args, stdin="", env=None, cwd=None):
        e = dict(os.environ)
        e.pop("TASK_SECURITY_GATE", None)
        e.update(env or {})
        return subprocess.run([sys.executable, GATE] + args, input=stdin, capture_output=True, text=True, env=e, cwd=cwd or self.ws)

    def test_hook_pre_deny_json(self):
        r = self.run_gate(["hook", "pre"], json.dumps({"tool_name": "Read", "tool_input": {"file_path": ".env"}, "cwd": self.ws}))
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "deny")

    def test_hook_pre_allow_is_silent(self):
        r = self.run_gate(["hook", "pre"], json.dumps({"tool_name": "Read", "tool_input": {"file_path": "app.js"}, "cwd": self.ws}))
        self.assertEqual(r.stdout.strip(), "")

    def test_hook_bypass_env(self):
        r = self.run_gate(["hook", "pre"], json.dumps({"tool_name": "Read", "tool_input": {"file_path": ".env"}, "cwd": self.ws}),
                          env={"TASK_SECURITY_GATE": "off"})
        self.assertEqual(r.stdout.strip(), "")

    def test_hook_fail_closed(self):
        r = self.run_gate(["hook", "pre"], "not json")
        self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")
        with open(os.path.join(self.ws, ".claude", "task-security.json"), "w") as f:
            f.write("{broken")
        r = self.run_gate(["hook", "pre"], json.dumps({"tool_name": "Read", "tool_input": {"file_path": "app.js"}, "cwd": self.ws}))
        self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_hook_post_seals_mcp_output(self):
        secret = FAKE["aws-access-key-id"]
        data = {"tool_name": "mcp__ticket__get_issue", "tool_response": [{"type": "text", "text": "comment: key " + secret}], "cwd": self.ws}
        r = self.run_gate(["hook", "post"], json.dumps(data))
        notice = json.loads(r.stdout)["hookSpecificOutput"]["updatedMCPToolOutput"]
        self.assertNotIn(secret, notice)
        self.assertIn("withheld", notice)
        clean = dict(data, tool_response="nothing to see")
        self.assertEqual(self.run_gate(["hook", "post"], json.dumps(clean)).stdout.strip(), "")
        not_mcp = dict(data, tool_name="Bash")
        self.assertEqual(self.run_gate(["hook", "post"], json.dumps(not_mcp)).stdout.strip(), "")

    def test_scan_run(self):
        secret = FAKE["github-token"]
        r = self.run_gate(["scan-run", "--", "printf 'ok\\n%s\\n'" % secret])
        self.assertNotIn(secret, r.stdout)
        self.assertIn("withheld", r.stdout)
        r = self.run_gate(["scan-run", "--", "echo clean; exit 3"])
        self.assertEqual(r.stdout.strip(), "clean")
        self.assertEqual(r.returncode, 3)
        saved = os.path.join(self.ws, "ev", "Q1.txt")
        self.run_gate(["scan-run", "--save", saved, "--", "printf '%s\\n'" % secret])
        with open(saved) as f:
            self.assertNotIn(secret, f.read())

    def test_classify(self):
        self.assertTrue(self.run_gate(["classify", "--", "git status"]).stdout.startswith("allow"))
        self.assertTrue(self.run_gate(["classify", "--", "printenv"]).stdout.startswith("deny"))
        self.assertTrue(self.run_gate(["classify", "--readonly", "--", "aws dynamodb scan --table-name t"]).stdout.startswith("confirm"))
        self.assertTrue(self.run_gate(["classify", "--readonly", "--", "git push"]).stdout.startswith("deny"))

    def test_scan_and_scan_diff(self):
        secret = FAKE["slack-token"]
        out = os.path.join(self.ws, "out.md")
        with open(out, "w") as f:
            f.write("all good\n")
        self.assertEqual(self.run_gate(["scan", out]).returncode, 0)
        with open(out, "a") as f:
            f.write("token " + secret + "\n")
        r = self.run_gate(["scan", out])
        self.assertEqual(r.returncode, 1)
        self.assertNotIn(secret, r.stdout)
        self.assertIn("out.md:2", r.stdout)

        repo = os.path.join(self.ws, "repo")
        os.makedirs(repo)
        git = lambda *a: subprocess.run(["git", "-C", repo] + list(a), capture_output=True, check=True)
        git("init", "-q")
        with open(os.path.join(repo, "a.js"), "w") as f:
            f.write("const a = 1;\n")
        git("add", "a.js")
        git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
        self.assertEqual(self.run_gate(["scan-diff", repo]).returncode, 0)
        with open(os.path.join(repo, "a.js"), "a") as f:
            f.write("const k = '%s';\n" % FAKE["appsync-api-key"])
        r = self.run_gate(["scan-diff", repo])
        self.assertEqual(r.returncode, 1)
        self.assertIn("a.js:2", r.stdout)
        self.assertNotIn(FAKE["appsync-api-key"], r.stdout)
        subprocess.run(["git", "-C", repo, "checkout", "-q", "a.js"], check=True)
        with open(os.path.join(repo, ".env.local"), "w") as f:
            f.write(FAKE["dotenv-secret"] + "\n")
        r = self.run_gate(["scan-diff", repo])
        self.assertEqual(r.returncode, 0)  # untracked secret FILE: warning only, content never opened
        self.assertIn("secret-file-untracked .env.local", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=1)
