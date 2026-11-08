# task — spec-driven task workflow for Claude Code

Code tasks and investigation tasks, from ticket to deliverable, with a **security gate** that keeps secrets out of the model's context.

```
/task:init (once per project) → .claude/task-workflow.yml, .claude/task-security.json, .mcp.json
┌──────────── Security gate: hook on every tool call (sub-agents included), always on ────────────┐
/task:new <ticket> [repo] [--type code|investigate] [--from <task>] [--refresh]
   ▼   fetches description + all comments + attachments from the ticket system (read-only)
/task:spec        code: problem → solution          investigate: questions → hypotheses → criteria
   ▼              investigate: Expected deliverable (format, table rows × columns, cell values, template) fixed up front
/task:plan        code: [Cx] before/after + Verify   investigate: [Qx] commands + expected results
   ▼              every command classified by the gate (allow / confirm / deny)
   ▼              plan review: independent Opus agent checks coverage and commands; every auto fix applied once, ask items left to you (--no-review skips)
   ▼              smoke run (investigate): allow-class commands run once, 90 s cap; empty/error/timeout fixed once (--smoke-all, --no-smoke)
/task:implement   code: one agent per file, verify   investigate: read-only checks → evidence/
   ▼
/task:review      code: logic, checklists, verify, e2e, secret scan of the diff
   ▼              investigate: is every conclusion backed by evidence?   blockers → back to todo
/task:report      5_report.md (internal) + drafts in output_<review_language>/ for you to review
   ▼              draft check: independent Opus agent checks review fixes, traceability, format, writing rules; auto fixes applied (--no-check)
/task:report --final → output/ (translated, secret-scanned) — you post it; nothing is posted automatically
   └─ investigation done → /task:new <ticket>-fix --from <task> → a code task
```

## Install

**Your own machines** (editable; changes apply on the next session or `/reload-plugins`):
```sh
git clone git@github.com:tranhieptvh/task-workflow.git ~/.claude/skills/task
```
**Other people:**
```sh
claude plugin marketplace add tranhieptvh/task-workflow
claude plugin install task@task-workflow
```
**Requirement:** `python3` (3.8+). The security gate is a python hook; without python3 it cannot block anything, and every `/task:*` skill refuses to run.

## Workspace layout
Open Claude Code in a folder that holds the product repos side by side. Workflow files live there, outside every product repo's git:
```
<workspace>/
├── CLAUDE.md                 project knowledge
├── .mcp.json                 project MCP servers (Playwright, Context7)
├── .claude/
│   ├── task-workflow.yml     workflow config (read by the skills)
│   ├── task-security.json    project additions to the security policy (read by the gate)
│   ├── checklists/           review rules
│   └── task-templates/       your own deliverable templates (optional)
├── tasks/<ticket-id>/        one folder per task (below)
├── <repo-a>/  <repo-b>/      product repos
```
Task folder:
```
tasks/<id>/
├── .repo .type .security.log
├── 1_requirements.md … 5_report.md   internal working documents
├── assets/           input: ticket attachments, customer documents
├── evidence/         proof: command output, verify logs, e2e screenshots (.sealed/ = withheld output)
├── scripts/          throw-away scripts (when needed)
├── output_<lang>/    drafts for you to review (e.g. output_vi/comment/)
└── output/           final deliverables (comment/, report/, chat/)
```
One task = one ticket. A ticket may have several tasks (an investigation and its fix).

## Configuration — `.claude/task-workflow.yml`
Created by `/task:init`. Every key is optional; missing features are skipped (the security gate is always on).

| Key | Default | Meaning |
|---|---|---|
| `language` | language of the request | messages and working documents |
| `tasks_dir` | `tasks` | task folders |
| `repos` | `{default: "."}` | `default` repo and `list` of repos |
| `knowledge` | `[CLAUDE.md]` | files every sub-agent reads first |
| `search_paths` | whole repo | where spec/plan look for code (relative to the repo) |
| `checklists` | `[]` | `{match, file[#section]}` rules checked by implement and review |
| `review_lanes` | `[{name: Code, match: "**"}]` | one reviewer per lane (inline review when ≤ 3 files) |
| `integrations.ticket` | — | `{tool: backlog\|jira\|redmine\|github, mcp_server: <name>}` |
| `integrations.e2e` | — | `{base_url, envs: {<env>: {auth: storage-state\|explicit\|none, state_file, setup, write_guard}}, evidence_dir, no_screenshot}` |
| `integrations.docs` | — | `{context7: true}` |
| `verify` | `[]` | `{name, run, when: [implement, review], timeout, repo}`; placeholders `{changed_files}`, `{task_id}`, `{repo}`; `repo` limits an entry to tasks of that repo |
| `output` | review = final = `language`, markdown | `{review_language, languages, markup: markdown\|backlog\|jira\|textile, templates}` |

Example:
```yaml
language: vi
repos: { default: app, list: [app, admin] }
knowledge: [CLAUDE.md]
checklists:
  - { match: "src/api/**", file: ".claude/checklists/frontend.md#api" }
review_lanes:
  - { name: Frontend, match: "src/**" }
  - { name: Backend,  match: "backend/**" }
integrations:
  ticket: { tool: backlog, mcp_server: backlog }
verify:
  - { name: lint, run: "npx eslint {changed_files}", when: [implement, review] }
  - { name: e2e,  run: "npx playwright test --grep @{task_id}", when: [review], timeout: 900 }
output: { review_language: vi, languages: [ja], markup: backlog }
```

## MCP servers
| Server | Used by | Where | Installed by |
|---|---|---|---|
| Ticket (Backlog, Jira, Redmine…) | `/task:new` | user scope (`~/.claude.json`) | **you**, with your own API key — `/task:init` prints the command; the model never sees keys |
| Playwright (`@playwright/mcp`, pinned) | `/task:review` e2e | workspace `.mcp.json` | `/task:init` (`--isolated --storage-state <file>`; `--image-responses omit` for sensitive envs) |
| Context7 (`@upstash/context7-mcp`, pinned, off by default) | spec/plan library docs | workspace `.mcp.json` | `/task:init` when you opt in (it sends library names to an external service) |
| GitHub issues | `/task:new` | — | `gh` CLI, no MCP |

Versions are pinned (never `@latest`). The output of **every** MCP tool passes the security gate.

**E2E login:** the model never sees or types passwords. `storage-state` envs log in once (your setup script or you, by hand) and reuse the saved session file (treated as a secret). `explicit` envs (login writes real data) require your confirmation and the env's write guard. When the session expires the model stops and asks you to refresh it.

## Security gate
Secrets must never reach the model (everything in its context is sent to the cloud). The gate is a `PreToolUse`/`PostToolUse` hook, active in every session where the plugin is enabled, for the main agent and every sub-agent:

- **Secret files** (`.env*`, keys, `~/.aws`, `~/.ssh`, `~/.claude.json`, `.npmrc`…) cannot be read, searched, edited or touched by shell commands. Templates (`*.example`, `*.sample`, `*.template`) stay readable.
- **Secret-printing commands** are refused: `env`, `printenv`, `aws configure get …secret…`, `secretsmanager get-secret-value`, `ssm … --with-decryption`, `lambda get-function`, `sts assume-role`, `gh auth token`…
- **Safe forms only** for `lambda get-function-configuration` (env var names via `keys(Environment.Variables)`), `appsync list-api-keys` (no `id` — it IS the key), `ssm get-parameter` (no `Value`).
- **Output scanner:** `git show/diff`, `git log -p`, `git grep`, `git cat-file -p` (also with `git -C <dir>` and other global options) and `aws logs …` must run through `gate.py scan-run`, which prints the output only when no secret-like value is found; otherwise it is sealed in `.sealed/` (unreadable by the model) and only the rule and line are reported. Names/stats/counts-only forms (`--stat`, `--name-only`, `git grep -c/-l`) need no scan. MCP tool output is scanned the same way before the model receives it.
- **Content Grep over a directory** needs a `type` or `glob` (Grep reads hidden files such as `.env.local`).
- **Read-only investigations:** while `/task:implement` runs an investigation (`tasks/<id>/.readonly`), write/deploy commands are refused, file writes are limited to the task folder, and data reads (`dynamodb scan`, `curl`, unclassified commands) ask you first.
- **Protected files:** the gate itself and Claude Code settings (where hooks could be disabled) cannot be modified by the model — including through `cd <dir> && …` and stdin scripts (`python3 - <<EOF`).
- **Fail-closed:** a gate error refuses the call. Exception: if `python3` is missing the hook cannot run at all — hence the python check in every skill.
- **Emergency switch:** start Claude Code with `TASK_SECURITY_GATE=off`. Only you can do this; commands mentioning the variable are refused.
- Events (no values) are logged to `tasks/<id>/.security.log`, or `~/.claude/task-security/security.log` when no task is active.

Project additions go to `.claude/task-security.json` — they can only **tighten** the default policy:
```json
{
  "secret_paths": ["e2e/.auth/*"],
  "secret_patterns": [{"id": "myapp-key", "regex": "MYAPP_[A-Z]+_KEY=\\S+"}],
  "commands": {"allow": ["amplify status"], "confirm": ["amplify pull *"], "deny": ["amplify push *"]}
}
```
`commands` apply during read-only investigations; `allow` only covers commands the default policy does not classify.

Command-line helpers:
```
python3 security/gate.py scan-run [--save FILE] -- '<command>'   print output only if clean
python3 security/gate.py scan <path|-> ...                       list secret-like matches (rule + location)
python3 security/gate.py scan-diff <repo>                        scan lines added since HEAD
python3 security/gate.py classify [--readonly] -- '<command>'    allow | confirm | deny
```

**Limits.** The gate prevents *accidental* exposure; it is not a sandbox against a model deliberately obfuscating commands. Pattern scanning can miss secrets with unusual formats (e.g. a plain lowercase password), and images (screenshots, attachments) cannot be scanned — blocking secret sources is the primary defence.

## Templates
Deliverables are written from templates: `comment.code`, `comment.investigate`, `report`, `chat` (in `templates/`). Override or add your own in `<workspace>/.claude/task-templates/<name>.md` (e.g. `comment.security`); a task picks them in its spec (`Expected deliverable → Template`), otherwise `output.templates` and the defaults apply. Writing rules for drafts (tone, scope, naming) go in a file listed under `knowledge`, so the spec writer and the draft check both read them. Drafts are written in `output.review_language` and the ticket's markup; `--final` translates them into `output.languages`, re-scans for secrets and checks that every translation keeps the same facts.

## Contributing
- The plugin stays project-agnostic: no project paths, framework names or rule IDs in `skills/` — those belong in the project's config and checklists.
- `python3 security/test_gate.py` must pass before every commit.
- Design notes and the change history of v0.2 are in `ROADMAP.md`.
