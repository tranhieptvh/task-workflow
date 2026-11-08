---
name: plan
description: Read 2_spec.md of the active task and the codebase, then write 3_plan.md — atomic change items [Cx] for a code task, check items [Qx] with commands and expected results for an investigation — classify every command with the security gate, then have an independent Opus agent review the plan and smoke-run the read-only commands before implementation.
argument-hint: "[--force] [--no-review] [--no-smoke | --smoke-all]"
---

Read `../../reference/common.md` (relative to this skill's base directory) and run Step 0 completely.

## 1. Validate
- `$T/2_spec.md` missing or a placeholder → stop: "Run `/task:spec` first."
- `$T/3_plan.md` not a placeholder → overwrite rule (`--force`); warn that `[x]` statuses are lost.

## 2. Explore sub-agent (foreground)
Explore returns its findings as its final message; the main session writes them to `$T/.scout.md`.
```
Return your findings as your final message (no file writes), in <language>.
<security paragraph from common.md>
Read the knowledge files: <knowledge>. Read `$T/2_spec.md`.
<code> For each file/function to change: locate it (Grep), read only that part, record full path from the workspace root (`$REPO/...`, no `./` when the repo is `.`), line, function and the current code.
<investigate> For each hypothesis: find the code paths and resource names involved, so checks can name exact functions, tables, log groups and resources.
Format: ## Findings / ### <name> / - File / - Line / - Function / - Current code / - Deps
```

## 3. Writer (general-purpose, foreground)
```
<security paragraph from common.md>
Read `$T/2_spec.md` and `$T/.scout.md`. Write `$T/3_plan.md` in <language>; keep `## [Cx]`/`## [Qx]` and the field labels in English.

---
task: $TASK
repo: $REPO
type: $TYPE
status: todo
---
```
For `code`, one item per atomic change (one function or block in one file; several places in a file → several items):
```
## [C1] Short change name
- **Status:** [ ] todo
- **File:** `$REPO/path/to/file:line`
- **Deps:** (empty = independent | C2 = C2 first)
- **Description:** one sentence
- **Verify:** (optional) a fast, non-interactive command proving this item, e.g. a self-check script the item creates
- **Change:**
  ```
  // Before:
  <current code>
  // After:
  <new code>
  ```
```
For `investigate`, one item per check:
```
## [Q1] Short check name
- **Status:** [ ] todo
- **Hypothesis:** H1 (from the spec)
- **Source:** code | logs | database | cloud resource — exact name
- **Env/Profile:** <environment> / <aws profile or "local">
- **Commands:**
  ```
  <exact command(s); AWS always with --profile; prefer --query to select only needed fields>
  ```
- **Expect if true:** …
- **Expect if false:** …
- **Deps:** (empty | Q2)
```
Rules: no command may print secrets (use the safe forms: Lambda env → names only, no `--with-decryption`, compare values locally as same/different). No write/deploy command in an investigation — a change belongs to a separate task (`/task:new <id>-fix --from <task>`).
Then delete `$T/.scout.md`.

## 4. Security classification (G2, main session)
For every command in `Commands:` (investigate) and every `Verify:` (code), run:
`$GATE classify [--readonly] -- '<command>'` (`--readonly` for investigate items)
and add under the item: `- **Security:** allow | confirm | deny — <rule>`.
- `deny` → rewrite the command in the safe form the gate suggests and classify again; if no safe form exists, remove it and add the item to a section `## Needs a separate task` with the reason.
- Collect every `confirm` command.

## 5. Plan review (independent agent, Opus)
Skipped with `--no-review`. Catches plan defects before anything runs: missing coverage, commands that cannot return what the item needs, wrong before-code.

Launch one general-purpose agent, foreground, with `model: "opus"`. Give it only the prompt below — no summary of steps 2–4 — so it judges the plan independently.
```
Review the plan of task $TASK before it is implemented, in <language>. Return the review as your final message (no file writes, no shell commands).
<security paragraph from common.md>
Read the knowledge files: <knowledge>; then $T/1_requirements.md, $T/2_spec.md, $T/3_plan.md. Read code (Grep/Read) wherever you need to check a claim of the plan.
Check:
1. Coverage — <investigate> every spec question and hypothesis has at least one [Qx]; <code> every part of the Proposed solution and Scope has a [Cx]. Every environment, region, profile, branch and repo in the spec's scope is covered. Name what is missing.
2. <investigate> Each command returns what its Expect lines rely on: glob/pathspec matching, sort order, pagination or truncation, --region/--profile, shell quoting, --query fields, data volume (will it finish?). Expect if true / if false really separate the hypothesis; name items whose result can only be an inference.
   <code> Before matches the current file (line and content); After implements the spec; callers and imports affected by the change are covered (Grep them); Deps are right; the After code respects the checklists <checklists matching each File>; Verify really proves the item.
3. Scope — items outside the spec; write/deploy commands in an investigation.
Report only real problems, no style remarks. Format (bullets, no headings starting with "## [" — other skills parse those):
## Plan review
- Result: ✅ ok | ⚠️ N warnings | ❌ N blockers
- **[Q6]** blocker — <what is wrong, quoting the command/line> · Fix: <concrete change to the plan>
- **[General]** warning — …
Blocker = the item would produce a wrong or incomplete result. Warning = it works but the result is weaker.
```
Then, in the main session:
- Append the review to the end of `$T/3_plan.md` (replace an existing `## Plan review` section).
- **One revision round for blockers:** edit the affected items as the Fix says; classify new or changed commands again (step 4); append ` → fixed` or ` → not fixed: <reason>` to each blocker bullet. Do not run the reviewer again — what is left goes to the user.

## 6. Smoke run (investigate only, main session)
Skipped with `--no-smoke` and for `code` tasks. Catches what reading cannot: a pathspec that matches nothing, a quoting error, a query that never finishes. It tests the final commands, so it runs after the plan review.

Which commands: those whose step-4 classification is `allow`. With `--smoke-all`, also `confirm` ones (the gate asks the user for each). Never `deny`.
For each command:
1. Replace each `<placeholder>` with one concrete value named in the plan or spec (the first function / branch / env). No such value → `skipped (placeholder)`.
2. Run with the Bash tool's timeout set to 90 s:
   `$GATE scan-run --save $T/.smoke/<Qx>-<n>.txt -- '<command>' > /dev/null; echo "exit=$?"; wc -l < $T/.smoke/<Qx>-<n>.txt; head -15 $T/.smoke/<Qx>-<n>.txt`
3. Judge against the item's Expect lines:
   - `ok` — exits 0 and returns the fields the Expect lines rely on. A sealed result counts as `ok` (the data exists).
   - `empty` — no output, or a count of 0, where the Expect lines need data (wrong pathspec, filter, region, profile) → blocker.
   - `error: <first error line>` — syntax, usage or quoting error → blocker. Permission errors (AccessDenied, Forbidden) are not plan bugs: note that the result will be 未確認 / not confirmed and say so in Expect.
   - `timeout` → blocker: narrow it (shorter time range, one sample per day, fewer resources) and say in Expect that the result is a sample.
Add under the item: `- **Smoke:** ok | empty | error: … | timeout | skipped (confirm / placeholder)`.
**One fix round:** rewrite each blocker command, classify it again (step 4), run it once more and update its Smoke line. Still failing → leave it and list it for the user.
Then delete `$T/.smoke/` — implement produces the real evidence.

## 7. Report
```
✅ $T/3_plan.md created — N items · plan review: X blockers (Y fixed), Z warnings | skipped · smoke: A ok, B fixed, C failing, D skipped | skipped
<investigate> Commands that will ask for confirmation when run (read-only mode): <list with env/profile>
<not fixed blockers, warnings and failing smoke commands, one line each>
👉 Review the plan, then run /task:implement --all (or /task:implement C1 C2 / Q1 Q2)
```
