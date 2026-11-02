---
name: init
description: Set up the task workflow in a workspace — detect repos, choose the ticket system, languages, verify commands, e2e and MCP servers, then write .claude/task-workflow.yml, .claude/task-security.json and .mcp.json. Run once per project, again to fill gaps.
argument-hint: "[key=value ...]  e.g. ticket=backlog:backlog review_language=vi languages=ja markup=markdown verify=detect e2e=none context7=no"
---

Read `../../reference/common.md` (relative to this skill's base directory) first. Run its Step 0 item 1 (gate check) only — this skill creates the config.

## 1. Workspace
`$WS` = current directory.
- If `$WS/.git` exists, the workspace IS a product repo. Warn: "Workflow files are best kept outside product repos: create a parent folder, move the repo inside, and open Claude Code in the parent." If the user continues anyway, at the end add the workflow paths (`.claude/task-workflow.yml`, `.claude/task-security.json`, `.claude/checklists/`, `.claude/task-templates/`, `.mcp.json`, `tasks/`) to `$WS/.git/info/exclude` (create the lines only if missing).
- If `.claude/task-workflow.yml` already exists: read it, keep every existing value, and only ask about missing keys. Never overwrite existing keys.

## 2. Answers
Arguments `key=value` pre-answer questions. Ask the rest with AskUserQuestion. **If AskUserQuestion is not available (non-interactive run), do not stop: use the defaults below, write the files, and list every assumed value in the summary** — the user changes them by editing the files or rerunning `/task:init key=value`.

| Key | Question | Default |
|---|---|---|
| `repos` | Product repos (comma separated) | every directory up to depth 3 that contains `.git` (skip `node_modules`) |
| `ticket` | Ticket system and MCP server name, `<tool>:<server>` (`backlog`, `jira`, `redmine`, `github`, `none`) | `none` |
| `review_language` | Language the user reviews drafts in | language of the request |
| `languages` | Languages of the final deliverables (comma separated) | `review_language` |
| `markup` | Markup of the ticket system: `markdown`, `backlog`, `jira`, `textile` | `markdown` |
| `verify` | `detect` (suggest from package.json / Makefile, user confirms) or `none` | `detect` |
| `e2e` | `none`, or `<env>:<auth>[:<state_file>]` per env (auth = `storage-state`, `explicit`, `none`), comma separated | `none` |
| `context7` | Library docs lookup through Context7 (sends library names to an external service) | `no` |

## 3. Ticket MCP
For `ticket=<tool>:<server>` (not `github`, not `none`): check whether tools named `mcp__<server>__*` are available in this session.
- Available → note "ticket MCP ok".
- Missing → print, for the USER to run (the model never runs it and never handles keys), the install template from `../../reference/ticket-systems.md` ("Installing the MCP server"). Continue; do not block.
For `github`: run `gh auth status` and report the result line only.

## 4. Verify commands (`verify=detect`)
For each repo read `package.json` `scripts` / `devDependencies` and `Makefile` targets (do not run anything). Suggest only cheap, non-interactive commands, for example:
- eslint present (or `react-scripts`) → `{ name: lint, run: "npx eslint {changed_files}", when: [implement, review] }`
- prettier present → `{ name: format, run: "npx prettier --check {changed_files}", when: [review] }`
- a real test script that terminates (not a watcher) → `{ name: test, run: "<script>", when: [review], timeout: 600 }`
- playwright config present → `{ name: e2e, run: "npx playwright test --grep @{task_id}", when: [review], timeout: 900 }`
With several repos, add `repo: <dir>` to each entry so it only runs for tasks of that repo. Show the list and let the user keep/remove items.

## 5. E2E (Playwright MCP) and Context7
For each e2e env with a browser (`auth` = `storage-state` or `explicit`), add to `$WS/.mcp.json` a server `playwright-<env>`:
```json
{"command": "npx", "args": ["-y", "@playwright/mcp@0.0.83", "--isolated", "--output-dir", "<$WS>/tasks/.e2e"]}
```
- `storage-state` → add `"--storage-state", "<absolute state_file>"`, and add the state file to `security.secret_paths` (it contains tokens).
- Ask whether pages show secrets; if yes add `"--image-responses", "omit"`.
- Record in the workflow config `integrations.e2e` (base_url, envs with auth/state_file/setup/write_guard, evidence_dir, no_screenshot).
`context7=yes` → add `"context7": {"command": "npx", "args": ["-y", "@upstash/context7-mcp@4.4.4"]}` and `integrations.docs.context7: true`.
Merge into an existing `.mcp.json`: add servers, never remove or change existing ones. Versions stay pinned (no `@latest`).

## 6. Write the files
- `$WS/.claude/task-workflow.yml` — every chosen value, with a one-line comment per section. Include `repos`, `knowledge` (CLAUDE.md if present), `integrations`, `verify`, `output`.
- `$WS/.claude/task-security.json` — only project additions (may stay `{}`): `{"secret_paths": [...], "secret_patterns": [], "commands": {"allow": [], "confirm": [], "deny": []}}`. Projects can only add restrictions; explain that `commands` apply during read-only investigations. Example for a deploy CLI: allow `"<cli> status"`, confirm `"<cli> pull *"`, deny `"<cli> push *"`.
- `$WS/tasks/` (empty, with `.current` absent).

## 7. Summary
```
✅ Workflow set up in <WS>
Repos: …   Ticket: … (MCP ok | install command printed)   Languages: review <x> → final <y>
Verify: …   E2E: …   Context7: on/off
Connectors (claude.ai): <list of mcp__claude_ai_* servers present, or none>
Security gate: active in every session (python3 ok). Emergency off switch: start Claude Code with TASK_SECURITY_GATE=off (the user only).
Assumed (non-interactive): …
👉 Next: /task:new <ticket-id>
```
