---
name: bplan
description: Backend-focused implementation planning. Fork of plan. Includes backend design analysis and design language management.
---

# /bplan - backend implementation plan

Stage 2.2 of 4: issue -> design -> bplan -> implement -> ship.

## Rules (all stages)

- No emojis anywhere: plan files, commit messages, PR titles/bodies, PR comments.
- The handoff file is the workflow state carrier. Always read it first; never rely on conversation memory.
- Never edit product code in this skill. Only read it to write the plan.
- Minimize new code. Favor extending or reusing existing helpers, store methods, API routes, CLI commands, and patterns. Each step should touch the smallest possible surface area.
- write a line at the end of the handoff file for each step, showing which files it touches, which existing code it reuses, and why nothing existing fits if new code is needed.

## Resolve (shared by all four skills)

Input is an issue number or a PR number.
- PR number: `gh pr view <N> --repo alekoHalkias/Emusync --json body,headRefName,state` and read the issue from `Closes #X`.
- Issue number: `git fetch --prune`, then find the branch with `git branch -a --list "*/<N>-*"` and the handoff at `tools/plans/<N>-handoff.md` on that branch.

Stage:
| State | Next skill |
|---|---|
| No branch or no handoff file | bplan |
| Plan has unchecked `- [ ]` steps (`Status: planned` = awaiting approval) | implement |
| All steps checked, `PR: none` | ship |
| `PR: #M` and status `shipped` | done - report it |
| `Status: blocked` | stop, show the failure report |

If invoked at the wrong stage, say so and invoke the right skill.

## Steps

1. Resolve the issue number. `gh issue view <N> --repo alekoHalkias/Emusync --json number,title,body,comments` and read all of it.

2. Read the handoff file at `tools/plans/<N>-handoff.md`. If it does not exist, create it using the template from the `issue` skill, filling in the Issue and Design sections from the GitHub issue and any existing plan file.

3. Branch. If no `*/<N>-*` branch exists: `git fetch --prune && git branch -r`, stop and flag any `feature/*` or `copilot/*` branch touching the same files; otherwise `git checkout main && git pull && git checkout -b feature/<N>-<slug>`. If it exists, check it out. Never work on `main`.

4. Backend Design Management:
   - Load/Create Design Guide: Read `.claude/backend-design-guide.md`. If it doesn't exist, create it by analyzing `server/`, `cli/`, and `emusync.py`.
   - Discovery: Analyze current backend patterns (API routes, store methods, CLI commands, sync logic, auth, config handling).
   - Update Guide: If the current issue introduces a new, reusable backend pattern or modifies an existing one, update `.claude/backend-design-guide.md`.
   - Maintenance: If the guide exceeds 100 lines, compress it by merging similar patterns and removing redundant examples.

5. Read the code. Trace the real flow end to end through every file the change touches. Consult CLAUDE.md Rules and the relevant section of docs/ARCHITECTURE.md / docs/GOTCHAS.md; the plan must comply with every rule that applies. Focus on Python, FastAPI, SQLite/Store, Click, and mDNS.

6. Design Alignment:
   - Compare the requested changes in the issue against `.claude/backend-design-guide.md`.
   - If the request conflicts with current patterns, suggest modifications to fit the project format.
   - If no design principle exists for a requested change, propose a recommendation based on the established style and update the guide.

7. Reuse search (required, primary strategy). Every step must start by searching for existing code that already does what is needed — helpers, store methods, API routes, CLI commands, utilities. Extend or call existing code rather than writing parallel copies. New code is a last resort and requires a one-line justification explaining why nothing existing fits. If a step can be done by modifying one existing function call, that is preferred over adding a new function.

8. If a design decision is genuinely open (data shape, DB schema, protocol, etc.), ask the user. Do not ask what the code can answer.

9. If the work is too big for one reviewable PR, propose splitting into separate issues and stop.

10. Write `tools/plans/<N>-<slug>.md` (the executable plan file):
    ```
    # Plan: #<N> <issue title>

    Issue: #<N>
    Branch: feature/<N>-<slug>
    PR: none
    Status: planned
    Fix attempts: 0

    ## Goal
    One sentence.

    ## Design Alignment
    - **Backend Pattern**: <how this change fits/modifies existing backend patterns>
    - **Recommendations**: <if any, or "none">

    ## Steps
    - [ ] 1. <what changes, observable result>
      - Files: path/a.py, path/b.py
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

11. Update the handoff file. Rewrite section 4 (Backend Plan) with the Design Alignment results. Append any plan steps to section 8 (Implementation Steps), each annotated with files, reuses, and new-code justification. Update the Metadata section: set `Status: planned`. Append to the Log:
    ```
    - <YYYY-MM-DD> bplan: <N> steps written, backend_pattern=<summary>
    ```

12. Commit the plan file, design guide, and handoff file: `git add tools/plans/<N>-*.md .claude/backend-design-guide.md && git commit -m "Add backend implementation plan for #<N> with design alignment and guide update"`.

13. Show the plan to the user and stop. On approval, invoke `tplan` with the issue number. If they request changes, revise, recommit, re-present.

## Fix-plan mode (called by ship)

When ship passes failing test output: do steps 4-5 scoped to the failure, then append to the existing plan file (do not create a new issue, branch, or plan):
```
## Fix attempt <k>
Failure: <test id> - <error summary>
Cause: <identified cause>
- [ ] F<k>.1 ...
```
Update the handoff file: append to section 11 (Fix Attempts) and the Log. Commit it and invoke `implement` directly - no user approval pause in this mode.
