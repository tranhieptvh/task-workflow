---
name: implement
description: Carry out the items of 3_plan.md for the active task — edit code ([Cx]) and run verify commands, or run read-only investigation checks ([Qx]) and record evidence. Use --all for every todo item, or list item IDs.
argument-hint: "[--all | C1 C2 ... | Q1 Q2 ...]"
---

Read `../../reference/common.md` (relative to this skill's base directory) and run Step 0 completely.

## 1. Validate and select
- `$T/3_plan.md` missing or a placeholder → stop: "Run `/task:plan` first."
- Parse items (`## [Cx]` / `## [Qx]`): Status, File, Deps, Verify, Commands, Security.
- `--all` → every `[ ] todo` item. IDs → only those (already done → "Cx already done, skipped"; unknown → error).
- An item whose Deps are not done and not in this run → skip: "C3 waits for C2".
- Nothing left → say so and suggest `/task:review`.

## 2a. Code task ([Cx])
**Group by file** — one general-purpose agent per file, items in ID order, so no two agents edit the same file. Groups without outside Deps run in parallel (background); a group depending on another starts after that group's items report `done` (if one reports `error`, do not start it).

Agent prompt:
```
Task: $TASK · Repo: $REPO · File: <file> · Items (in order): <ids>
<security paragraph from common.md>
Read the knowledge files first: <knowledge>
For each item in order:
1. Read the `## [<item>]` section of `$T/3_plan.md` (Description, Change).
2. Read the target file (offset/limit). Re-read before each item: earlier edits shift lines.
3. Apply the change with Edit. Only edit <file> (plus a new file the item explicitly creates).
4. Check the edited code against these checklists: <checklist files whose match fits the file, or "none">.
Do NOT edit `$T/3_plan.md` and do NOT run shell commands.
Return one line per item: <id> | done/error | note.
```

**After each group (main session):**
1. For every item reported `done`: Edit `$T/3_plan.md`, old_string spanning the `## [Cx] …` heading through its `- **Status:** [ ] todo` line (unique) → `- **Status:** [x] done`. Only the main session writes this file.
2. Verify, through the gate scanner, from the repo directory:
   - each done item's `Verify:` command
   - each `verify` entry of the config with `when` containing `implement` (skip entries whose `repo` is not `$REPO`), `{changed_files}` = files of this group
   `cd $REPO && $GATE scan-run --save $T/evidence/verify-<name-or-item>.log -- '<command>'` (timeout from config, default 300 s).
   Add under the item `- **Verify result:** pass | fail — <first failing line or summary>`. A failure does not undo `done` and is not retried automatically: report it.

## 2b. Investigation task ([Qx]) — read-only
1. Create `$T/.readonly` (empty). While it exists the gate blocks write/deploy commands and file writes outside `$T`, and asks the user before commands marked `confirm`.
2. Show the user the `confirm` commands of the selected items (env/profile and reason) before starting.
3. Run the items in dependency order **in the main session** (sub-agents do not run commands). For each command:
   `$GATE scan-run --save $T/evidence/<Qx>-<n>.txt -- '<command>'`
   - Refused by the gate → do not work around it; record "refused: <rule>" and continue.
   - "Output withheld" → record "value exists, withheld (secret-like data)".
4. Compare the evidence with `Expect if true` / `Expect if false` and add under the item:
   `- **Result:** confirmed | rejected | inconclusive — <one sentence> (evidence: evidence/<Qx>-<n>.txt)`
   then mark the item `[x] done` (same Edit rule as 2a).
5. **Always delete the marker at the end** with `rm -f <tasks_dir>/$TASK/.readonly` run from the workspace root (no `cd`), also when stopping on an error. If you cannot, tell the user to delete it.

Non-interactive runs: commands classified `confirm` cannot be confirmed and are refused — record them as "not run: needs confirmation" and continue with the others.

## 3. Summary
```
✅ Done: C1, C2 (path/file) … | Q1 confirmed, Q2 rejected …
⚠️ Verify failed: C3 (lint: 2 errors) …
⏭️ Skipped: C4 (already done) | C5 (waits for C4)
⛔ Refused by the security gate: … (if any)
👉 Still todo: … — /task:implement <ids>   or all done → /task:review
```
