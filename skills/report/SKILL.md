---
name: report
description: Summarise the active task into 5_report.md and draft the deliverables (ticket comment, report, chat message) from templates for the user to review; --final translates the approved drafts into output/ after a secret scan.
argument-hint: "[--final] [--with report,chat] [--force]"
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
- Template per deliverable: `$WS/.claude/task-templates/<name>.md` if it exists, else `../../templates/<name>.md` (relative to this skill's base directory).
- Always: the ticket comment — `output.templates.<type>` (default `comment.code` / `comment.investigate`) → `$DRAFT/comment/comment.md`.
- `--with report` → `report` template → `$DRAFT/report/report.md`; `--with chat` → `chat` template → `$DRAFT/chat/chat.md`.
- Write in `$R`, in the markup `output.markup`:

| markup | headings | bullets | bold | code |
|---|---|---|---|---|
| markdown | `## H` | `- x` | `**b**` | ``` |
| backlog | `** H` | `- x` | `''b''` | `{code}…{/code}` |
| jira | `h2. H` | `* x` | `*b*` | `{code}…{code}` |
| textile | `h2. H` | `* x` | `*b*` | `<pre>…</pre>` |

- Content rules: results only; no local paths, script names, file appendices or configuration values; only what matters for the ticket's scope; methods in words.
- Run `$GATE scan $DRAFT` — any match: rewrite the passage without the value and scan again.

### 4. Report
```
✅ 5_report.md written · drafts: $DRAFT/comment/… (+report, chat)
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
