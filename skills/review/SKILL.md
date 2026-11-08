---
name: review
description: Review the active task — code tasks against the spec, checklists, verify commands, e2e and a secret scan of the diff; investigation tasks on whether every conclusion is backed by evidence. Writes 4_review.md and reopens blocker items.
argument-hint: "[--force]"
---

Read `../../reference/common.md` (relative to this skill's base directory) and run Step 0 completely.

## 1. Validate
- `$T/3_plan.md` missing or a placeholder → stop: "Run `/task:plan` first."
- No `[x] done` item → stop: "Nothing implemented yet. Run `/task:implement` first."
- `4_review.md` is regenerated on every run (no overwrite question).

## 2a. Code task
Run these checks; each produces findings for 4_review.md.

1. **Secret scan of the changes (G4).** For every repo touched by the plan: `$GATE scan-diff <repo>`.
   - `secret …` lines → blocker on the item owning that file ("secret-like value added in <file>:<line>"; never quote it).
   - `warn secret-file-untracked …` → warning only (a secret file exists but is not ignored by git; the user should add it to `.gitignore`). Not a blocker of the task.
   Also `$GATE scan tasks/<id>/evidence` (sealed files are skipped).
2. **Verify.** In the main session, every config `verify` entry with `when` containing `review` (skip entries whose `repo` is not `$REPO`) plus every item's `Verify:` command, through `cd $REPO && $GATE scan-run --save $T/evidence/verify-<name>.log -- '<command>'` (`{changed_files}` = all files of done items, `{task_id}` = $TASK). Failure → blocker on the related item (or a general blocker).
   No `verify` configured and no item Verify → note "no verify configured — run /task:init" (not a blocker).
3. **E2E (A2)** — only if `integrations.e2e` is configured and `mcp__playwright-<env>__*` tools exist:
   - User starts the app. Check `base_url` answers (`curl -s -o /dev/null -w '%{http_code}' <base_url>`); not reachable → note and skip.
   - Follow the scenario of `1_requirements.md` (reproduction steps or acceptance criteria) with the Playwright tools. Never type passwords. If the app shows a login page in `storage-state` mode: stop e2e and tell the user to refresh the session with the env's `setup` command. In `explicit` mode logging in writes data: ask the user first and require the env's `write_guard`.
   - Do not screenshot pages listed in `no_screenshot`. Save screenshots/notes to `$T/evidence/e2e/`.
   - A failed scenario → blocker on the related item.
4. **Logic & checklists (lanes).** Assign done-item files to `review_lanes` (first match wins; others → lane `Other`) with their checklists (`file#section` = only that heading).
   - **3 files or fewer in total → review inline** in the main session (B2).
   - Otherwise one Explore agent per non-empty lane (parallel, background), returning the review as its final message:
   ```
   Review lane <name>, in <language>. Return the review as your final message (no file writes).
   <security paragraph from common.md>
   Read the knowledge files: <knowledge>; the "Proposed solution" of $T/2_spec.md.
   Files and items: <file → item IDs, line, checklists>
   For each item: read the changed code; Logic (matches the spec? cases missed?); Scope (changes outside the plan?);
   Checklist (cite rule ID + line for each violation).
   Format: ### [Cx] name — `path:line` / - Logic / - Scope / - Checklist / - Fix
   ```

## 2b. Investigation task
Review inline (or one general-purpose agent when there are more than 8 items) — evidence first:
- Every done `[Qx]` has a `Result` and its evidence file exists in `$T/evidence/` (a sealed result counts as evidence of existence only).
- Every hypothesis of the spec is confirmed, rejected or explicitly inconclusive; every spec question has an answer or is marked open.
- Every cell of the spec's Expected deliverable table (if any) can be filled from a done `[Qx]` Result, with a value allowed by the spec; a cell without a source → blocker ("<row> × <column> has no evidence").
- Conclusions follow from the evidence: flag claims without evidence, results that contradict each other, and places where a result is an inference.
- Commands refused by the gate: is the conclusion still valid without them?
- `$GATE scan $T/evidence` → any match outside `.sealed` is a blocker ("evidence contains secret-like data").
Missing evidence or an unsupported conclusion → blocker on that item.

## 3. Write `$T/4_review.md` (in <language>, headings translated, keep `[Cx]`/`[Qx]`)
```
---
task: $TASK
type: $TYPE
reviewed: <today, ISO date>
---
## Summary
- ✅ X passed | ⚠️ Y warnings | ❌ Z blockers
- Verify: <pass/fail per command or "not configured"> · Secret scan: clean | N findings · E2E: <result or "not configured">
## Items
### [Cx] name
- **Status:** ✅ pass / ⚠️ warning / ❌ blocker
- **File:** `path`
- **Finding:** (empty if pass)
- **Fix:** (empty if pass)
## Blockers — re-implement
- **Cx** — short problem → `/task:implement Cx`
```
⚠️ warning = minor, does not affect correctness. ❌ blocker = wrong vs spec, checklist violation, out of scope, verify/e2e failure, secret found, unsupported conclusion.

## 4. Reopen blockers
For each blocker item, Edit `$T/3_plan.md` (old_string from the `## [Cx]` heading through its Status line) → `- **Status:** [ ] todo`.

## 5. Report
```
✅ Review done — X passed, Y warnings, Z blockers   ($T/4_review.md)
(blockers) ❌ Fix first: /task:implement C2 C4
(none)     👉 /task:report
```
