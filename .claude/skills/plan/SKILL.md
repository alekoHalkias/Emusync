---
name: plan
description: Read a GitHub issue and the code it touches, then write a reuse-first, step-by-step implementation plan to tools/plans/<issue>-<slug>.md on the issue's feature branch. Use when the user runs /plan <issue|PR>, after /issue, or when ship needs a fix plan for failing tests. Never edits product code.
---

# /plan - write the plan file

Stage 2 of 4: issue -> plan -> implement -> ship. Never edit product code in this skill.

## Rules (all stages)

- No emojis anywhere: plan files, commit messages, PR titles/bodies, PR comments.
- The plan file and GitHub are the only workflow state. Never rely on conversation memory.

## Resolve (shared by all four skills)

Input is an issue number or a PR number.
- PR number: `gh pr view <N> --repo alekoHalkias/Emusync --json body,headRefName,state` and read the issue from `Closes #X`.
- Issue number: `git fetch --prune`, then find the branch with `git branch -a --list "*/<N>-*"` and the plan at `tools/plans/<N>-*.md` on that branch.

Stage:
| State | Next skill |
|---|---|
| No branch or no plan file | plan |
| Plan has unchecked `- [ ]` steps (`Status: planned` = awaiting approval) | implement |
| All steps checked, `PR: none` | ship |
| `PR: #M` and status `shipped` | done - report it |
| `Status: blocked` | stop, show the failure report |

If invoked at the wrong stage, say so and invoke the right skill.

## Steps

1. Resolve the issue number. `gh issue view <N> --repo alekoHalkias/Emusync --json number,title,body,comments` and read all of it.
2. Branch. If no `*/<N>-*` branch exists: `git fetch --prune && git branch -r`, stop and flag any `feature/*` or `copilot/*` branch touching the same files; otherwise `git checkout main && git pull && git checkout -b feature/<N>-<slug>`. If it exists, check it out. Never work on `main`.
3. Read the code. Trace the real flow end to end through every file the change touches. Consult CLAUDE.md Rules and the relevant section of docs/ARCHITECTURE.md / docs/GOTCHAS.md; the plan must comply with every rule that applies.
4. Reuse search (required). For each piece of logic the work needs, grep for an existing helper, store method, route, CLI command, IPC handler, type, or component that does it or nearly does. Extend or call it instead of writing a parallel copy. New code is allowed only with a one-line reason why nothing existing fits.
5. If a design decision is genuinely open (data shape, UX, which layer owns it), ask the user. Do not ask what the code can answer.
6. If the work is too big for one reviewable PR, propose splitting into separate issues and stop.
7. Write `tools/plans/<N>-<slug>.md`:
   ```
   # Plan: #<N> <issue title>

   Issue: #<N>
   Branch: feature/<N>-<slug>
   PR: none
   Status: planned
   Fix attempts: 0

   ## Goal
   One sentence.

   ## Steps
   - [ ] 1. <what changes, observable result>
     - Files: path/a.py, path/b.ts
     - Reuses: path/a.py:existing_fn
     - New: <thing> - <why nothing existing fits>
   - [ ] 2. ...
   - [ ] N. Tests: <test file, cases>. No mocks, real SQLite.
   - [ ] N+1. Docs: CLAUDE.md / docs/ARCHITECTURE.md updates, or "none needed - <why>".

   ## Checklist
   Schema bump: yes/no. New IPC channel (+ emusync.d.ts): yes/no. New CLI subcommand: yes/no. Config/data file change: yes/no.

   ## Not in this plan
   ## Log
   ```
   Steps must be small enough to finish and verify one at a time.
8. Commit the plan file only: `git add tools/plans/<N>-*.md && git commit -m "Add implementation plan for #<N>"`.
9. Show the plan to the user and stop. On approval, invoke `implement` with the issue number. On requested changes, revise, recommit, re-present.

## Fix-plan mode (called by ship)

When ship passes failing test output: do steps 3-4 scoped to the failure, then append to the existing plan file (do not create a new issue, branch, or plan):
```
## Fix attempt <k>
Failure: <test id> - <error summary>
Cause: <identified cause>
- [ ] F<k>.1 ...
```
Commit it and invoke `implement` directly - no user approval pause in this mode.
