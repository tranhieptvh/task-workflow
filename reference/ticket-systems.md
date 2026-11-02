# Ticket systems

`integrations.ticket` in `.claude/task-workflow.yml`:
```yaml
integrations:
  ticket:
    tool: backlog          # backlog | jira | redmine | github
    mcp_server: backlog    # name of the MCP server (tools are mcp__<mcp_server>__*); not used for github
```

## Fetching a ticket (read-only)
Fetch **everything**: summary/metadata, description, **all** comments (follow pagination until no more pages, oldest first) and **all** attachments.
Never change the ticket: no comment, status, assignee or field update.

| Tool | Metadata + description | Comments (paginate) | Attachments |
|---|---|---|---|
| backlog | `get_issue` (issueIdOrKey) | `get_issue_comments` (order asc; page with `minId` = last id until empty) | list from `get_issue`'s `attachments`; content via `get_issue_attachment` |
| jira | get issue (fields: summary, status, assignee, description, attachment) | issue comments (`startAt` until `total`) | `attachment` field; download each |
| redmine | `issues/<id>.json?include=journals,attachments` | `journals` (notes only) | `attachments[].content_url` |
| github | `gh issue view <n> --json title,state,assignees,body,url` | `gh issue view <n> --comments --json comments` | links in body/comments (not downloaded) |

Tool names for jira and redmine depend on the MCP server installed; match them by purpose. If a needed tool does not exist, say which one and continue with what is available.

## Attachments
- When the tool returns the file content, write it to `$T/assets/<original name>`.
- When it returns only metadata or a URL that needs auth, list it under "Attachments (not downloaded)" with name and size.
- After saving, run `$GATE scan $T/assets`. For every file reported, move it to `$T/evidence/.sealed/` and note in `1_requirements.md`: "<name>: withheld by the security gate (contains secret-like data)". Images cannot be scanned for secrets by pattern — mention this once if there are images.
- MCP output itself is scanned by the gate before you receive it. A result saying "[security gate] Output withheld" means a secret was in that ticket data: record "part of the ticket was withheld (secret-like data)" and continue with the rest (e.g. fetch comments page by page so only the affected page is withheld).

## 1_requirements.md layout
```
# <KEY> — <title>

- **Ticket:** <KEY> · <status> · <assignee> · <url>
- **Fetched:** <ISO date-time> (comments up to id <last id>)

## Description
<description, verbatim>

## Comments
### <date> — <author> (id <id>)
<text, verbatim>
...

## Attachments
- `assets/<name>` (<size>)
- <name> — not downloaded: <reason>
```
`--refresh`: fetch again, append only comments whose id is greater than the recorded last id and attachments not yet in `assets/`, then update the "Fetched" line.

## Installing the MCP server (done by the USER, never by the model)
`/task:init` prints the command for the user to run; the model never types or reads API keys.
```
claude mcp add <name> --scope user -e <API_KEY_VAR>=<YOUR_API_KEY> [-e ...] -- <command of the server's README>
```
- Scope **user**: the key belongs to the person, is stored in `~/.claude.json` (blocked by the gate) and never enters a repo.
- Pin the server version exactly (no `@latest`).
- GitHub issues need no MCP server: `gh` must be authenticated (`gh auth status`).
