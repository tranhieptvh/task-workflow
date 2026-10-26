---
name: implement
description: Implement items from 3_plan.md of the active task. Use --all for every todo item, or list item IDs (e.g. C1 C2).
argument-hint: [--all | C1 C2 ...]
---

## Step 0 — Load config and task
Read `.claude/task-workflow.yml` if it exists. Defaults for missing keys:
`language` = language of the user's request · `tasks_dir` = `tasks` · `repos.default` = `.` · `knowledge` = `[CLAUDE.md]` if that file exists, else `[]` · `checklists` = `[]`

Read `<tasks_dir>/.current` → `$TASK`. Missing → stop: "No active task. Run `/task:new <id>` first."
Read `<tasks_dir>/$TASK/.repo` → `$REPO` (missing → `repos.default`). Let `$T` = `<tasks_dir>/$TASK`.

A file is a **placeholder** if it contains `<!-- task:placeholder` (legacy: `> Chưa có`).
Write all messages in `language`.

## Step 1 — Validate
`$T/3_plan.md` missing or a placeholder → stop: "Run `/task:plan` first."

## Step 2 — Select items
Parse `$T/3_plan.md`: for each `## [Cx]` take Status, File (path before `:line`), Deps.

- `--all` → every item with `[ ] todo`; `[x] done` items are skipped (idempotent)
- List of IDs → only those; already done → "Cx already done, skipped."; unknown ID → clear error
- An item whose Deps point to an item that is not done **and** not in this run → drop it: "C3 waits for C2 (not done)."

Nothing left → say so and suggest `/task:review`.

## Step 3 — Group by file and spawn agents
**Group:** items with the same file → one group, ordered by ID. One **agent per group**, so no two agents edit the same file.

**Checklists for a group:** every `checklists` entry whose `match` glob (relative to `$REPO`) matches the file. `file#section` means only that heading section of the file.

**Order:**
- Groups with no Deps outside the group (or whose Deps are already done) → spawn in parallel (background)
- Groups depending on another group → spawn after that group finishes and the depended-on items report `done`; if one reports `error`, do not spawn and list it under Error

general-purpose agent prompt:
```
Task: $TASK · Repo: $REPO · File: <file> · Items (in order): <ids>

First read the knowledge files: <knowledge>

For each item, in order:
1. Read the `## [<item>]` section of `$T/3_plan.md`: Description and Change (before/after)
2. Read the target file (offset/limit, not the whole file if large). Re-read before each item: earlier edits shift line numbers.
3. Apply the change with Edit. Only edit <file>.
4. Check the edited code against these checklists: <checklist files, or "none">

Do NOT edit `$T/3_plan.md` — the main session updates statuses.

Return one line per item: <item ID> | done/error | note (reason if error).
```

**Status update (main session, after each agent returns):** for each item reported `done`, Edit `$T/3_plan.md` with an `old_string` spanning the `## [Cx] ...` heading line through its `- **Status:** [ ] todo` line (unique match) → `- **Status:** [x] done`. Only the main session writes this file.

## Step 4 — Summary
```
✅ Done: C1, C2 (path/file), C3 (path/file2)
⏭️ Skipped: C4 (already done) | C5 (waits for C4)
❌ Error: (if any, with details)

👉 Still todo: C5, C6 — run /task:implement C5 C6
   Or all done → run /task:review
```
