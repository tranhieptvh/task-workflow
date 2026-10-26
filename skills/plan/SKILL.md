---
name: plan
description: Read 2_spec.md of the active task and the codebase, then write 3_plan.md with atomic change items (file:line, deps, before/after code).
---

## Step 0 — Load config and task
Read `.claude/task-workflow.yml` if it exists. Defaults for missing keys:
`language` = language of the user's request · `tasks_dir` = `tasks` · `repos.default` = `.` · `knowledge` = `[CLAUDE.md]` if that file exists, else `[]`

Read `<tasks_dir>/.current` → `$TASK`. Missing → stop: "No active task. Run `/task:new <id>` first."
Read `<tasks_dir>/$TASK/.repo` → `$REPO` (missing → `repos.default`). Let `$T` = `<tasks_dir>/$TASK`.

A file is a **placeholder** if it contains `<!-- task:placeholder` (legacy: `> Chưa có` or `<!-- Dán nội dung`).
Write all messages and generated files in `language`.

## Step 1 — Validate
- `$T/2_spec.md` missing or a placeholder → stop: "Run `/task:spec` first."
- `$T/3_plan.md` exists and is not a placeholder → ask: "`3_plan.md` already has content. Overwriting loses the current `[x]` statuses. Continue? (y/n)". Stop unless confirmed.

## Step 2 — Explore sub-agent (foreground)
Explore cannot write files: it returns the findings as its final message, and the main session writes them verbatim to `$T/.scout.md`.
Prompt:
```
Return your findings as your final message (no file writes).

Read the knowledge files: <knowledge>
Read `$T/2_spec.md` for the files involved and the proposed solution.

For each file/function to change:
1. Grep to locate the exact function/variable if no line number is known
2. Read only the part to change (offset/limit); never read large files in full
3. Record: full path from the workspace root, line, function name, current code

Format (in <language>):
## Findings
### <change name>
- File: `$REPO/path/to/file:line`
- Function: `name`
- Current code: (fenced block)
- Deps: (empty, or the other change that must happen first)
```

## Step 3 — general-purpose sub-agent (foreground, after Explore)
Prompt:
```
Read `$T/2_spec.md` and `$T/.scout.md`, then write `$T/3_plan.md` (in <language>; keep the `## [Cx]` headings and the field labels below exactly in English so other skills can parse them):

---
task: $TASK
repo: $REPO
status: todo
---

## [C1] Short change name
- **Status:** [ ] todo
- **File:** `$REPO/path/to/file:line`
- **Deps:** (empty = independent | C2 = C2 must be done first)
- **Description:** one sentence
- **Change:**
  ```
  // Before:
  <current code from .scout.md>

  // After:
  <new code per spec>
  ```

## [C2] ...

Rules:
- One item = one atomic change (one function or one block in one file)
- Paths are full from the workspace root
- Several places in one file → separate items (implement groups same-file items into one agent)
- Only set Deps when an item truly needs another first (e.g. uses a function the other creates)

Then delete `$T/.scout.md`.
```

## Step 4 — Report
```
✅ $T/3_plan.md created.
👉 Review the plan, then run:
   /task:implement --all     (everything)
   /task:implement C1 C2     (selected items)
```
