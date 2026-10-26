# task — spec-driven task workflow for Claude Code

```
/task:new <id> [repo]   → tasks/<id>/ with numbered placeholders, set as active task
   ↓ fill in 1_requirements.md
/task:spec              → 2_spec.md   (Explore scouts code → writer)
   ↓ review
/task:plan              → 3_plan.md   (atomic items [C1].. with file:line, deps, before/after)
   ↓ review
/task:implement --all   → one agent per file, parallel when independent
/task:implement C1 C2   → selected items only
   ↓
/task:review            → 4_review.md (one reviewer per lane; blockers are reopened)
   ↓ blockers? → /task:implement Cx → /task:review
/task:report            → 5_report.md
```

Task folder:
```
tasks/
├── .current            active task ID
└── <id>/
    ├── .repo           repo dir of this task
    ├── 1_requirements.md
    ├── 2_spec.md
    ├── 3_plan.md
    ├── 4_review.md
    ├── 5_report.md
    └── assets/         screenshots, PDFs, …
```

## Install

**Your own machines (editable, changes apply immediately):**
```sh
git clone git@github.com:tranhieptvh/task-workflow.git ~/.claude/skills/task
```
It loads as `task@skills-dir` on the next session (or run `/reload-plugins`).

**Other people:**
```sh
claude plugin marketplace add tranhieptvh/task-workflow
claude plugin install task@task-workflow
```
Update later with `claude plugin marketplace update task-workflow`.

## Project config — `.claude/task-workflow.yml`

Everything project-specific lives in the project, not in this plugin. The file is optional: without it the workflow runs on the whole repo with one review lane and no checklists.

| Key | Default | Meaning |
|-----|---------|---------|
| `language` | language of the request | Language of messages and generated files |
| `tasks_dir` | `tasks` | Where task folders live |
| `repos.default` | `.` | Repo dir used when `/task:new` gets none (workspaces with several repos) |
| `repos.list` | — | Valid repo dirs, shown when a wrong one is given |
| `knowledge` | `[CLAUDE.md]` if it exists | Files every sub-agent reads first (conventions, architecture) |
| `search_paths` | whole repo | Dirs (relative to repo) where spec/plan look for code |
| `checklists` | `[]` | `{match, file}`: rules checked by implement and review for files matching the glob. `file#section` = only that heading section |
| `review_lanes` | `[{name: Code, match: "**"}]` | `{name, match}`: one reviewer agent per lane; a file goes to the first matching lane, unmatched files to `Other` |

All paths are relative to the workspace root, except `match` and `search_paths`, which are relative to the task's repo.

Example:
```yaml
language: vi
repos:
  default: app
  list: [app, admin]
knowledge: [CLAUDE.md, docs/architecture.md]
search_paths: [src, backend]
checklists:
  - match: "src/api/**"
    file: .claude/checklists/frontend.md#api
  - match: "backend/**"
    file: .claude/checklists/backend.md
review_lanes:
  - name: Frontend
    match: "src/**"
  - name: Backend
    match: "backend/**"
```

A checklist is plain markdown: a table of rule IDs and rules. Reviewers cite the rule ID for each violation.

## Rules for contributing

The plugin must stay project-agnostic: no project paths, framework names or rule IDs in `skills/`. Those belong in the project's config and checklists.
