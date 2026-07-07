---
name: plan
description: Read the current branch's linked GitHub issue and draft an implementation plan for it, asking clarifying questions where the issue is ambiguous. Runs /implement once the plan is approved. Use when the user runs /plan, or automatically at the end of /issue.
---

# /plan — plan the current branch's issue

Follows CLAUDE.md's "Execution approval policy" — read-only commands run automatically, no confirmation needed. The "wait for approval" in step 7 is a deliberate workflow checkpoint on the *plan itself* (per the user's design for this pipeline), not a generic "may I run this command" gate — clarifying questions in step 4 are asked because the answer is genuinely unknown, not to seek permission.

## Steps

1. Get the current branch:
   ```bash
   git branch --show-current
   ```
   Extract the issue number from the `feature/<issue-number>-...` naming convention (CLAUDE.md). If the branch doesn't match that pattern (e.g. `main`, or an unlinked name), ask the user which issue number to plan for — do not guess.

2. Fetch the issue:
   ```bash
   export PATH="$HOME/.local/bin:$PATH"
   gh issue view <issue-number> --repo alekoHalkias/Emusync --json number,title,body,comments
   ```
   Fallback via curl + `GITHUB_TOKEN` if `gh` is unavailable:
   ```bash
   curl -s "https://api.github.com/repos/alekoHalkias/Emusync/issues/<issue-number>"
   curl -s "https://api.github.com/repos/alekoHalkias/Emusync/issues/<issue-number>/comments"
   ```

3. Read the issue title, body, and comments in full. Cross-reference CLAUDE.md's architecture/key-files tables and the actual code (not just the issue text) to figure out which files, IPC channels, DB tables, or components the work will actually touch.

4. If the issue is ambiguous or leaves a design/config decision open (data shape, UX behavior, naming, which layer owns something, edge-case handling), ask the user targeted clarifying questions before finalizing the plan. Don't ask about things you can resolve by reading the code. Don't ask "should I proceed" once the plan itself is clear — only ask what's genuinely undecided.

5. Draft the implementation plan: ordered steps, the specific files/modules each step touches, and which steps need new tests per CLAUDE.md's testing-requirements section (new API route, new Store method, new CLI subcommand, or a bug fix needing a regression test).

6. Present the plan to the user and stop — do not start editing code yet.

7. Wait for the user to approve the plan (e.g. "approved", "looks good", "proceed"). Once approved, invoke the `implement` skill (via the Skill tool) to carry it out through to PR — do not ask "should I proceed" again, approval of the plan is the go-ahead. If the user instead asks for changes to the plan, revise and re-present it before invoking `implement`.
