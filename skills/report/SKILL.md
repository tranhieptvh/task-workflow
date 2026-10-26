---
name: report
description: Summarise the active task from requirements to implementation and review results into 5_report.md.
---

## Step 0 — Load config and task
Read `.claude/task-workflow.yml` if it exists. Defaults for missing keys:
`language` = language of the user's request · `tasks_dir` = `tasks`

Read `<tasks_dir>/.current` → `$TASK`. Missing → stop: "No active task. Run `/task:new <id>` first."
Let `$T` = `<tasks_dir>/$TASK`.

A file is a **placeholder** if it contains `<!-- task:placeholder` (legacy: `> Chưa có` or `<!-- Dán nội dung`).
Write all messages and generated files in `language`.

## Step 1 — Validate
- `$T/1_requirements.md` is a placeholder → stop: "Fill in `1_requirements.md` first."
- `$T/2_spec.md` is a placeholder → stop: "Run `/task:spec` first."
- `$T/3_plan.md` is a placeholder → stop: "Run `/task:plan` first."
- `$T/5_report.md` exists and is not a placeholder → ask: "`5_report.md` already exists. Overwrite? (y/n)". Stop unless confirmed.

## Step 2 — general-purpose sub-agent (foreground)
Prompt:
```
Read `$T/1_requirements.md`, `$T/2_spec.md`, `$T/3_plan.md`, and `$T/4_review.md` if it exists and is not a placeholder.

Write `$T/5_report.md` (in <language>, headings translated):

---
task: $TASK
generated: <today, ISO date>
---

## Summary        — 1-2 sentences: what the task is, current state (done / in progress)
## Root cause     — from 2_spec.md, 2-4 sentences
## Implemented    — only [x] done items: - **[C1]** name — `path`
## Remaining      — [ ] todo items, or "All items are done."
## Review result  — only if 4_review.md was read: passed/warnings/blockers and open blockers, or "Passed review, no open blockers". Omit the section otherwise.
## Risks / monitor — from the Risks section of 2_spec.md
```

## Step 3 — Report
```
✅ $T/5_report.md created.
```
