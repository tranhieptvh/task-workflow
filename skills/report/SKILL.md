---
name: report
description: Summarise the active task into 5_report.md and draft the deliverables (ticket comment, report, chat message) from templates, have an independent Opus agent check and fix the drafts, then hand them to the user to review; --final translates the approved drafts into output/ after a secret scan.
argument-hint: "[--final] [--with report,chat] [--no-check] [--force]"
---

Read `../../reference/common.md` (relative to this skill's base directory) and run Step 0 completely.

Let `$R` = `output.review_language`, `$L` = `output.languages`, `$DRAFT` = `$T/output_$R` — or `$T/output` when `$L` is exactly `[$R]` (no translation step).

## A. Default run — internal report + drafts

### 1. Validate
- `1_requirements.md`, `2_spec.md`, `3_plan.md` must not be placeholders (say which command to run).
- `5_report.md` or `$DRAFT` already filled → overwrite rule (`--force`).

### 2. `5_report.md` (internal; general-purpose agent or inline)
```
<security paragraph from common.md>
Read 1_requirements.md, 2_spec.md, 3_plan.md and 4_review.md (if not a placeholder). Write $T/5_report.md in <language>:
---
task: $TASK
type: $TYPE
generated: <today, ISO date>
---
```
- `code`: `## Summary` (1–2 sentences, state) · `## Root cause` · `## Implemented` ([x] items: `**[C1]** name — path`) · `## Remaining` ([ ] items or "All items are done.") · `## Review result` (only if 4_review.md exists) · `## Risks / monitor`
- `investigate`: `## Answer` (to each spec question) · `## Root cause` · `## Confidence` (high/medium/low + why) · `## Evidence` (table: Qx · result · evidence file) · `## Not confirmed` (refused/withheld/inconclusive, with reason) · `## Next steps` (incl. `/task:new <id>-fix --from $TASK` when a fix is needed)
This file is internal: it may reference `evidence/` and `scripts/`.

### 3. Deliverable drafts
- Template name: the one the spec's `Expected deliverable → Template` names for that deliverable (`comment.*` for the comment, `report.*` for the report), else `output.templates.<type>` (comment) / `report` / `chat`, else the defaults below. File: `$WS/.claude/task-templates/<name>.md` if it exists, else `../../templates/<name>.md` (relative to this skill's base directory).
- Always: the ticket comment (default `comment.code` / `comment.investigate`) → `$DRAFT/comment/comment.md`. When the spec's Expected deliverable has a table, the comment and report use exactly its rows, columns and cell values.
- The report → `$DRAFT/report/report.md` when `--with report` is given or the spec's Expected deliverable lists a report; `--with chat` → `chat` template → `$DRAFT/chat/chat.md`.
- Write in `$R`, in the markup `output.markup`:

| markup | headings | bullets | bold | code |
|---|---|---|---|---|
| markdown | `## H` | `- x` | `**b**` | ``` |
| backlog | `** H` | `- x` | `''b''` | `{code}…{/code}` |
| jira | `h2. H` | `* x` | `*b*` | `{code}…{code}` |
| textile | `h2. H` | `* x` | `*b*` | `<pre>…</pre>` |

- Content rules: results only; no local paths, script names, file appendices or configuration values; only what matters for the ticket's scope; methods in words.
- Run `$GATE scan $DRAFT` — any match: rewrite the passage without the value and scan again.

### 4. Draft check (independent agent, Opus)
Skipped with `--no-check`. Checks the drafts before the user reads them, so the user does not have to ask for a double check.
Launch one general-purpose agent, foreground, with `model: "opus"`, given only this prompt:
```
Check the deliverable drafts of task $TASK before the user reviews them, in <language>. Return your findings as your final message (no file writes, no shell commands).
<security paragraph from common.md>
Read the knowledge files: <knowledge> (they hold the project's writing rules); then $T/1_requirements.md, $T/2_spec.md, the Result fields of $T/3_plan.md, $T/4_review.md (if not a placeholder) and every file in $DRAFT.
Check each draft:
1. Review fixes — every Fix in 4_review.md that changes a result, a wording or a label is reflected in the drafts.
2. Traceability — every conclusion, number and table cell comes from a done [Qx] Result or [Cx] item; flag statements without a source and inferences not labelled as inference.
3. Expected deliverable — the spec's format: sections, table rows × columns, allowed cell values, language.
4. Writing rules from the knowledge files and the content rules: ticket scope only; results only (no local paths, script names, configuration values); wording about other people.
Report only real problems. Format (bullets, no headings starting with "## ["):
## Draft check
- Result: ✅ ok | N findings (K auto, L ask)
- **[comment/comment.md]** auto — <problem, quoting the passage> · Fix: <exact replacement text>
- **[report/report.md]** ask — <problem> · Options: <a> / <b>
auto = a wording, label or format fix, or a missing review fix whose correct content is already in the plan results. ask = it changes a conclusion, adds or removes content, or needs information the task does not have.
```
Then, in the main session:
- Apply every `auto` Fix to the drafts in one round; append ` → applied` or ` → not applied: <reason>` to each bullet. Do not run the checker again.
- Append the check to the end of `$T/5_report.md` (replace an existing `## Draft check` section) — never into the drafts.
- Run `$GATE scan $DRAFT` again.

### 5. Report
```
✅ 5_report.md written · drafts: $DRAFT/comment/… (+report, chat) · draft check: A applied, B for you | skipped
<ask findings with their options, one line each>
👉 Review/edit the drafts in $DRAFT, then run /task:report --final
   (nothing is ever posted automatically)
```
(When `$DRAFT` is already `$T/output`, say the deliverables are final after review.)

## B. `--final` — translate the approved drafts
1. `$T/output_$R/` must exist and contain drafts; otherwise stop: "Run `/task:report` first." (If `$L` is `[$R]`, there is nothing to translate: run only step 3.)
2. For each draft file and each language in `$L`: translate faithfully (same sections, facts, numbers, markup) into `$T/output/<sub>/<name>.md` (one language) or `<name>.<lang>.md` (several). Never edit the final files by hand — they are regenerated from the drafts.
3. **G5 secret scan:** `$GATE scan $T/output $T/5_report.md`. Any match → do not report success; list file:line and rule, fix the draft, rerun `--final`.
4. **Parity check:** compare each translation with its draft section by section; list any missing or changed fact. Fix by regenerating.
5. Report:
```
✅ Final deliverables: $T/output/comment/comment.<lang>.md …  (secret scan: clean, parity: ok)
Post them yourself — the workflow never posts to the ticket or chat.
```
