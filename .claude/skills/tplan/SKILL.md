---
name: tplan
description: Testing-focused implementation planning. Reads fplan/bplan output and adds testing guidelines and steps.
---

# /tplan - testing implementation plan

Stage 2.3 of 4: issue -> design -> fplan/bplan -> implement -> ship.

## Rules (all stages)

- No emojis anywhere: plan files, commit messages, PR titles/bodies, PR comments.
- The handoff file is the workflow state carrier. Always read it first; never rely on conversation memory.
- Never edit product code in this skill. Only read it to write the plan.
- Minimize new test code. Favor extending or reusing existing test helpers, fixtures, and patterns. Each test step should leverage what is already available.
- write a line at the end of the handoff file for each step, showing which files it touches, which existing code it reuses, and why nothing existing fits if new code is needed.

## Resolve (shared by all four skills)

Input is an issue number or a PR number.
- PR number: `gh pr view <N> --repo alekoHalkias/Emusync --json body,headRefName,state` and read the issue from `Closes #X`.
- Issue number: `git fetch --prune`, then find the branch with `git branch -a --list "*/<N>-*"` and the handoff at `tools/plans/<N>-handoff.md` on that branch.

Stage:
| State | Next skill |
|---|---|
| No branch or no handoff file | tplan |
| Plan has unchecked `- [ ]` steps (`Status: planned` = awaiting approval) | implement |
| All steps checked, `PR: none` | ship |
| `PR: #M` and status `shipped` | done - report it |
| `Status: blocked` | stop, show the failure report |

If invoked at the wrong stage, say so and invoke the right skill.

## Steps

1. Resolve the issue number. `gh issue view <N> --repo alekoHalkias/Emusync --json number,title,body,comments` and read all of it.

2. Read the handoff file at `tools/plans/<N>-handoff.md`. If it does not exist, create it using the template from the `issue` skill, filling in the Issue and Design sections from the GitHub issue and any existing plan file.

3. Branch. If no `*/<N>-*` branch exists: `git fetch --prune && git branch -r`, stop and flag any `feature/*` or `copilot/*` branch touching the same files; otherwise `git checkout main && git pull && git checkout -b feature/<N>-<slug>`. If it exists, check it out. Never work on `main`.

4. Testing Design Management:
   - Load/Create Test Guide: Read `.claude/testing-guide.md`. If it doesn't exist, create it by analyzing `src/tests/` and existing test patterns in the codebase.
   - Discovery: Analyze current testing patterns (integration test structure, fixtures, SQLite usage, CLI testing, Electron IPC testing).
   - Update Guide: If the current issue introduces a new, reusable testing pattern or modifies an existing one, update `.claude/testing-guide.md`.
   - Maintenance: If the guide exceeds 100 lines, compress it by merging similar patterns and removing redundant examples.

5. Read the existing plan. Load `tools/plans/<N>-<slug>.md` from either `fplan` or `bplan`.

6. Test Alignment:
   - Compare the existing plan against `.claude/testing-guide.md`.
   - Identify gaps: missing test cases, insufficient coverage, edge cases not addressed.
   - If no testing principle exists for a planned change, propose recommendations based on the established style and update the guide.

7. Reuse search (required, primary strategy). Every step must start by searching for existing test helpers, fixtures, utilities, and patterns that cover the case. Extend or call existing test infrastructure rather than writing parallel copies. New test code is a last resort and requires a one-line justification explaining why nothing existing fits. If a test case can be added by extending an existing fixture or parameterizing an existing test, that is preferred over writing a new test function.

8. If a testing decision is genuinely open (test structure, mock vs real DB, coverage depth), ask the user. Do not ask what the code can answer.

9. If the testing scope is too big for one reviewable PR, propose splitting into separate issues and stop.

10. Update `tools/plans/<N>-<slug>.md`:
    - Add a `## Testing` section before `## Checklist`
    - Insert test steps into the existing plan steps
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
    - **Visual Pattern** / **Backend Pattern**: <how this change fits existing patterns>
    - **Recommendations**: <if any, or "none">

    ## Steps
    - [ ] 1. <what changes, observable result>
      - Files: path/a.ts, path/b.tsx
      - Reuses: path/a.ts:existing_fn
      - New: <thing> - <why nothing existing fits>
    - [ ] 2. ...
    - [ ] N. Tests: <test file, cases>. No mocks, real SQLite.
    - [ ] N+1. Docs: CLAUDE.md / docs/ARCHITECTURE.md updates, or "none needed - <why>".

    ## Testing
    - **Test File**: <path to test file>
    - **Test Cases**:
      - <case 1>: <description>
      - <case 2>: <description>
    - **Edge Cases**:
      - <edge case 1>: <description>
    - **Integration Points**:
      - <integration point 1>: <description>

    ## Checklist
    Schema bump: no. New IPC channel (+ emusync.d.ts): yes/no. New CLI subcommand: no. Config/data file change: no.

    ## Not in this plan
    ## Log
    ```
    Steps must be small enough to finish and verify one at a time.

11. Update the handoff file. Rewrite section 6 (Testing Plan) with the test file, test cases, edge cases, and integration points. Update the Metadata section: set `Status: planned`. Append to the Log:
    ```
    - <YYYY-MM-DD> tplan: test_file=<path>, <N> test cases defined
    ```

12. Commit the plan file, test guide, and handoff file: `git add tools/plans/<N>-*.md .claude/testing-guide.md && git commit -m "Add testing plan for #<N> with test guidelines and guide update"`.

13. Show the plan to the user and stop. On approval, invoke `implement` with the issue number. If they request changes, revise, recommit, re-present.

## Fix-plan mode (called by ship)

When ship passes failing test output: do steps 4-5 scoped to the failure, then append to the existing plan file (do not create a new issue, branch, or plan):
```
## Fix attempt <k>
Failure: <test id> - <error summary>
Cause: <identified cause>
- [ ] F<k>.1 ...
```
Update the handoff file: append to section 11 (Fix Attempts) and the Log. Commit it and invoke `implement` directly - no user approval pause in this mode.
