---
name: spec
description: Analyse 1_requirements.md and the codebase of the active task, then write 2_spec.md (context, problem, proposed solution, scope, risks).
---

## Step 0 — Load config and task
Read `.claude/task-workflow.yml` if it exists. Defaults for missing keys:
`language` = language of the user's request · `tasks_dir` = `tasks` · `repos.default` = `.` · `knowledge` = `[CLAUDE.md]` if that file exists, else `[]` · `search_paths` = whole repo

Read `<tasks_dir>/.current` → `$TASK`. Missing → stop: "No active task. Run `/task:new <id>` first."
Read `<tasks_dir>/$TASK/.repo` → `$REPO` (missing → `repos.default`). Let `$T` = `<tasks_dir>/$TASK`.

A file is a **placeholder** if it contains `<!-- task:placeholder` (legacy: `> Chưa có` or `<!-- Dán nội dung`).
Write all messages and generated files in `language`.

## Step 1 — Validate
- `$T/1_requirements.md` missing → stop: "Missing `$T/1_requirements.md`."
- `$T/1_requirements.md` is a placeholder → stop: "Fill in `1_requirements.md` first."
- `$T/2_spec.md` exists and is not a placeholder → ask: "`2_spec.md` already has content. Overwrite? (y/n)". Stop unless confirmed.

## Step 2 — Explore sub-agent (foreground)
Explore cannot write files: it returns the findings as its final message, and the main session writes them verbatim to `$T/.scout.md`.
Prompt (substitute the values):
```
Return your findings as your final message (no file writes).

1. Read the knowledge files: <knowledge>
2. Read `$T/1_requirements.md` in full, and every file in `$T/assets/` if any
3. Extract keywords from the requirement: feature, function, page, error type
4. Grep + Glob for related files under `$REPO/<each search_path>`
5. For each related file read only the relevant part (offset/limit); never read large files in full
6. If it is a bug, identify the root cause

Sections (write in <language>, headings translated):
## Requirement summary   (3-5 sentences)
## Related files         (- `path` — role)
## Current behaviour     (current logic; cause chain if bug)
## Technical constraints (project patterns from the knowledge files that must be kept)
```

## Step 3 — general-purpose sub-agent (foreground, after Explore)
Prompt:
```
Read `$T/1_requirements.md` and `$T/.scout.md`, then write `$T/2_spec.md` in <language> (translate the section headings too):

---
task: $TASK
repo: $REPO
status: draft
---

## Context        — what the task is and where it came from
## Problem        — current behaviour in code and why it is wrong / missing
## Proposed solution — concrete approach that fits the project architecture
## Scope          — files/functions changed; features affected indirectly
## Risks          — what to watch out for when implementing

Then delete `$T/.scout.md`.
```

## Step 4 — Report
```
✅ $T/2_spec.md created.
👉 Review the spec, then run /task:plan
```
