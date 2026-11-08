# Common rules for every /task:* skill

## Paths
- **Plugin root** (`$PLUGIN`): two levels up from the skill's base directory (shown as "Base directory for this skill" when the skill loads).
- **Gate:** `$GATE` = `python3 $PLUGIN/security/gate.py`
- **Workspace** (`$WS`): the directory Claude Code was opened in. Workflow files live here, next to the product repos — never inside a product repo's git.

## Step 0 — run first in every skill
1. **Gate check.** Run `$GATE scan /dev/null`. It must print `result: clean`. Otherwise stop: "python3 is required by the task security gate (without it the gate cannot block anything). Install python3 and retry."
2. **Config.** Read `$WS/.claude/task-workflow.yml` if it exists. Defaults for missing keys:

| Key | Default |
|---|---|
| `language` | language of the user's request |
| `tasks_dir` | `tasks` |
| `repos.default` | `.` |
| `knowledge` | `[CLAUDE.md]` if it exists, else `[]` |
| `search_paths` | whole repo |
| `checklists` | `[]` — `{match: <glob relative to repo>, file: <path>[#section]}` |
| `review_lanes` | `[{name: Code, match: "**"}]` |
| `integrations` | none — `ticket`, `e2e`, `docs` (see the skills that use them) |
| `verify` | `[]` — `{name, run, when: [implement, review], timeout, repo}`; an entry with `repo` runs only for tasks of that repo |
| `output` | `{review_language: <language>, languages: [<language>], markup: markdown}` |

3. **Active task** (all skills except `new` and `init`): read `<tasks_dir>/.current` → `$TASK`; missing → stop: "No active task. Run `/task:new <id>` first." Let `$T` = `<tasks_dir>/$TASK`.
   - `$REPO` = content of `$T/.repo`. If missing → infer it from the paths in `$T/3_plan.md` (their first segment that is a directory in `$WS` containing `.git`), ask the user once to confirm, then write `$T/.repo`. If nothing can be inferred → `repos.default`.
   - `$TYPE` = content of `$T/.type`, default `code`.
4. **Language.** Write messages and generated files in `language` (headings translated). Keep `## [Cx]` / `## [Qx]` headings and the field labels `Status`, `File`, `Deps`, `Verify`, `Security`, `Smoke`, `Result` in English so other skills can parse them.

## Placeholders
A file is a placeholder if it contains `<!-- task:placeholder` (legacy: `> Chưa có`, `<!-- Dán nội dung`).

## Overwrite
When a skill would overwrite a file that is not a placeholder: ask the user, unless the arguments contain `--force`. In a non-interactive run (no way to ask) without `--force`, stop and say how to rerun with `--force`.

## Task folder
```
$T/
├── .repo .type .security.log
├── 1_requirements.md … 5_report.md   internal working documents
├── assets/          INPUT: ticket attachments, documents from the customer
├── evidence/        PROOF produced while working (command output, verify logs, screenshots); .sealed/ = withheld output
├── scripts/         throw-away scripts (create only when needed)
├── output_<lang>/   deliverables for the user to review, e.g. output_vi/comment/
└── output/          final deliverables to send, e.g. output/comment/, output/report/
```
Create `evidence/`, `scripts/`, `output*/` only when there is something to put in them. Never move old tasks' files.

## Security — mandatory for the skill AND for every sub-agent prompt
The task security gate (a hook) blocks secret files and secret-printing commands. Add this paragraph verbatim to **every** sub-agent prompt:

> Security: never read or print secrets (.env files, keys, credentials, tokens, environment values). If a tool call is refused with "[security gate] …", follow its hint (narrower command, --query, a `type`/`glob` for Grep); never try to work around it. Never write secret values into any file.

Rules for the skill itself:
- Call the gate by its **full literal path** (`python3 /…/security/gate.py …`), never through a shell variable or alias: the gate must recognise its own command.
- Run commands from the workspace root and give task files as paths from there (`tasks/<id>/…`), without `cd` into the task folder: the gate resolves relative paths against the session directory.
- Commands whose output may contain secrets (logs, `git show`, `git log -p`, `git diff`) run through `$GATE scan-run [--save <file>] -- '<command>'`.
- AWS: always pass `--profile` explicitly. Use only the safe forms the gate suggests (e.g. Lambda env → names only).
- Never try to read `*/.sealed/*`. A sealed result means "the value exists and was withheld": report that fact, not the value.
- Compare secret values only locally and print `same` / `different`.
- Deliverables in `output*/` contain results only — no local paths, script names or file appendices; describe methods in words; never configuration values.

## Sub-agents
- Pass the knowledge files (`knowledge`) to every sub-agent and tell it to read them first.
- Explore agents cannot write files: they return their result as their final message and the main session writes it.
- Sub-agents never run shell commands for verification; the main session does (so every command passes the gate once, in one place).
