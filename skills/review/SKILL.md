---
name: review
description: Review the implemented items of the active task against 2_spec.md and the project's checklists, write 4_review.md, and reopen blocker items. Run after /task:implement, before /task:report.
---

## Step 0 — Load config and task
Read `.claude/task-workflow.yml` if it exists. Defaults for missing keys:
`language` = language of the user's request · `tasks_dir` = `tasks` · `repos.default` = `.` · `knowledge` = `[CLAUDE.md]` if that file exists, else `[]` · `checklists` = `[]` · `review_lanes` = `[{name: Code, match: "**"}]`

Read `<tasks_dir>/.current` → `$TASK`. Missing → stop: "No active task. Run `/task:new <id>` first."
Read `<tasks_dir>/$TASK/.repo` → `$REPO` (missing → `repos.default`). Let `$T` = `<tasks_dir>/$TASK`.

A file is a **placeholder** if it contains `<!-- task:placeholder` (legacy: `> Chưa có`).
Write all messages and generated files in `language`.

## Step 1 — Validate
- `$T/3_plan.md` missing or a placeholder → stop: "Run `/task:plan` first."
- No `[x] done` item → stop: "Nothing implemented yet. Run `/task:implement` first."

## Step 2 — Assign files to lanes
From the `[x] done` items take ID and File. Assign each file to the **first** lane in `review_lanes` whose `match` (relative to `$REPO`) matches it; files matching no lane go to a lane named `Other`.
For each file also collect its checklists: every `checklists` entry whose `match` matches (`file#section` = only that heading section).

## Step 3 — One Explore agent per non-empty lane (parallel, background)
Explore cannot write files: each agent returns its review as its final message, and the main session writes it verbatim to `$T/.review-<lane>.md`.
Prompt:
```
Review lane: <lane name>. Return the review as your final message (no file writes), in <language>.

Read the knowledge files: <knowledge>
Read the "Proposed solution" section of `$T/2_spec.md`.

Files and items: <file → item IDs, line from plan, checklists>

For each item:
1. Read the changed code (offset/limit around the plan's line)
2. Logic — does it do what the spec asks? Any case missed?
3. Scope — any change outside the files/functions in the plan? Unwanted side effects?
4. Checklists — check against each listed checklist; cite the rule ID and line for any violation

Format:
## <lane name> review
### [Cx] item name — `path:line`
- **Logic:** ✅ matches spec / ❌ wrong — what exactly
- **Scope:** ✅ / ❌ — what
- **Checklist:** ✅ / ❌ — rule ID + line (omit if no checklist)
- **Fix:** (empty if pass)
```

## Step 4 — general-purpose agent (foreground, after all lanes finish)
Prompt:
```
Read `$T/3_plan.md` ([x] done items), `$T/2_spec.md`, and every `$T/.review-*.md`.

Write `$T/4_review.md` (overwrite, in <language>, headings translated; keep `[Cx]` IDs):

---
task: $TASK
reviewed: <today, ISO date>
---

## Summary
- ✅ X passed | ⚠️ Y warnings | ❌ Z blockers

## Items
### [Cx] item name
- **Status:** ✅ pass / ⚠️ warning / ❌ blocker
- **File:** `path`
- **Finding:** (empty if pass)
- **Fix:** (empty if pass)

## Blockers — re-implement
(only if any blocker)
- **Cx** — short problem → run `/task:implement Cx`

Rules:
- No problems → summary is just "✅ All X items passed."
- ⚠️ warning = minor, does not affect correctness (style, naming, could be better)
- ❌ blocker = logic wrong vs spec, checklist violation, or change outside scope

Then delete every `$T/.review-*.md`.
```

## Step 5 — Reopen blockers
Blocker items are still `[x] done`, so `/task:implement Cx` would skip them. For each blocker, Edit `$T/3_plan.md` (old_string spanning the `## [Cx]` heading through its Status line) → `- **Status:** [ ] todo`.

## Step 6 — Report
```
✅ Review done — X passed, Y warnings, Z blockers
$T/4_review.md

(blockers) ❌ Fix before continuing:
  /task:implement C2 C4

(no blockers) 👉 Run /task:report
```
