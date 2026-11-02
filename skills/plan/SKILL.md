---
name: plan
description: Read 2_spec.md of the active task and the codebase, then write 3_plan.md — atomic change items [Cx] for a code task, check items [Qx] with commands and expected results for an investigation — and classify every command with the security gate.
argument-hint: "[--force]"
---

Read `../../reference/common.md` (relative to this skill's base directory) and run Step 0 completely.

## 1. Validate
- `$T/2_spec.md` missing or a placeholder → stop: "Run `/task:spec` first."
- `$T/3_plan.md` not a placeholder → overwrite rule (`--force`); warn that `[x]` statuses are lost.

## 2. Explore sub-agent (foreground)
Explore returns its findings as its final message; the main session writes them to `$T/.scout.md`.
```
Return your findings as your final message (no file writes), in <language>.
<security paragraph from common.md>
Read the knowledge files: <knowledge>. Read `$T/2_spec.md`.
<code> For each file/function to change: locate it (Grep), read only that part, record full path from the workspace root (`$REPO/...`, no `./` when the repo is `.`), line, function and the current code.
<investigate> For each hypothesis: find the code paths and resource names involved, so checks can name exact functions, tables, log groups and resources.
Format: ## Findings / ### <name> / - File / - Line / - Function / - Current code / - Deps
```

## 3. Writer (general-purpose, foreground)
```
<security paragraph from common.md>
Read `$T/2_spec.md` and `$T/.scout.md`. Write `$T/3_plan.md` in <language>; keep `## [Cx]`/`## [Qx]` and the field labels in English.

---
task: $TASK
repo: $REPO
type: $TYPE
status: todo
---
```
For `code`, one item per atomic change (one function or block in one file; several places in a file → several items):
```
## [C1] Short change name
- **Status:** [ ] todo
- **File:** `$REPO/path/to/file:line`
- **Deps:** (empty = independent | C2 = C2 first)
- **Description:** one sentence
- **Verify:** (optional) a fast, non-interactive command proving this item, e.g. a self-check script the item creates
- **Change:**
  ```
  // Before:
  <current code>
  // After:
  <new code>
  ```
```
For `investigate`, one item per check:
```
## [Q1] Short check name
- **Status:** [ ] todo
- **Hypothesis:** H1 (from the spec)
- **Source:** code | logs | database | cloud resource — exact name
- **Env/Profile:** <environment> / <aws profile or "local">
- **Commands:**
  ```
  <exact command(s); AWS always with --profile; prefer --query to select only needed fields>
  ```
- **Expect if true:** …
- **Expect if false:** …
- **Deps:** (empty | Q2)
```
Rules: no command may print secrets (use the safe forms: Lambda env → names only, no `--with-decryption`, compare values locally as same/different). No write/deploy command in an investigation — a change belongs to a separate task (`/task:new <id>-fix --from <task>`).
Then delete `$T/.scout.md`.

## 4. Security classification (G2, main session)
For every command in `Commands:` (investigate) and every `Verify:` (code), run:
`$GATE classify [--readonly] -- '<command>'` (`--readonly` for investigate items)
and add under the item: `- **Security:** allow | confirm | deny — <rule>`.
- `deny` → rewrite the command in the safe form the gate suggests and classify again; if no safe form exists, remove it and add the item to a section `## Needs a separate task` with the reason.
- Collect every `confirm` command.

## 5. Report
```
✅ $T/3_plan.md created — N items
<investigate> Commands that will ask for confirmation when run (read-only mode): <list with env/profile>
👉 Review the plan, then run /task:implement --all (or /task:implement C1 C2 / Q1 Q2)
```
