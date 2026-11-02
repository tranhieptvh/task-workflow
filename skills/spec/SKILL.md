---
name: spec
description: Analyse 1_requirements.md and the codebase of the active task and write 2_spec.md — problem and solution for a code task, questions and hypotheses for an investigation task.
argument-hint: "[--force]"
---

Read `../../reference/common.md` (relative to this skill's base directory) and run Step 0 completely.

## 1. Validate
- `$T/1_requirements.md` missing or a placeholder → stop: "Fill in `1_requirements.md` first (or create the task from a ticket)."
- `$T/2_spec.md` is not a placeholder → overwrite rule of common.md (`--force`).

## 2. Explore sub-agent (foreground)
Explore cannot write files; the main session writes its final message verbatim to `$T/.scout.md`.
```
Return your findings as your final message (no file writes), in <language>.

<security paragraph from common.md>

1. Read the knowledge files: <knowledge>
2. Read `$T/1_requirements.md` and every text file in `$T/assets/`
3. Extract keywords (feature, function, page, error, resource, environment)
4. Grep/Glob under `$REPO/<each search_path>`; read only the relevant parts (offset/limit)
5. <code> Identify the cause chain if it is a bug.
   <investigate> List what is already known from code, what must be checked in which data source (code, logs, database, cloud resources) and in which environment/profile.
6. <if integrations.docs.context7 is true and context7 tools exist> Look up the APIs of the libraries involved, for the versions in the repo's package manifest.

Sections (headings translated):
## Requirement summary   (3–5 sentences)
## Related files         (- `path` — role)
## Current behaviour     (code: current logic / cause chain; investigate: known facts)
## Open points           (investigate: what needs data from outside the code, with source and environment)
## Technical constraints (project patterns from the knowledge files)
```

## 3. Writer (general-purpose, foreground)
```
<security paragraph from common.md>
Read `$T/1_requirements.md` and `$T/.scout.md`. Write `$T/2_spec.md` in <language> (headings translated):

---
task: $TASK
repo: $REPO
type: $TYPE
status: draft
---
```
For `code`:
```
## Context            — what the task is, where it came from
## Problem            — current behaviour and why it is wrong/missing
## Proposed solution  — concrete approach that fits the architecture
## Scope              — files/functions changed; features affected indirectly
## Risks              — what to watch when implementing
```
For `investigate`:
```
## Context            — what triggered the investigation
## Questions          — numbered questions this task must answer (Q-level, not commands)
## Hypotheses         — H1..Hn: each with what would confirm it and what would reject it
## Data sources       — code paths, logs, tables, cloud resources; environment + AWS profile for each
## Conclusion criteria — when the answer is considered established; what remains "inconclusive"
## Constraints        — read-only; environments/profiles allowed; data that must not be exported
## Risks              — e.g. production load, personal data in results
```
Then delete `$T/.scout.md`.

## 4. Report
```
✅ $T/2_spec.md created (<type>).
👉 Review the spec, then run /task:plan
```
