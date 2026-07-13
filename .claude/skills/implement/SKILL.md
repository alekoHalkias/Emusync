---
name: implement
description: Execute the plan drafted by /plan for the current branch's issue, write tests, verify, commit, push, and open the PR. Use when the user runs /implement, normally right after confirming a /plan.
---

# /implement — build the plan and ship the PR

Follows CLAUDE.md's "Execution approval policy" — runs straight through with no pauses once started. Only stop for the user if a step would directly modify something on the machine outside this repo, or if a genuine blocker comes up (conflicting branch, missing plan, failing test that reveals a wrong assumption) — surface those instead of guessing past them.

## Steps

1. Confirm there's a plan to work from: reuse the plan already drafted in this conversation by `/plan`. If none exists yet (fresh session, no plan in context), tell the user to run `/plan` first — do not invent a plan from the issue alone.

2. Sanity-check the branch: `git branch --show-current` should match `feature/<issue-number>-...` from the plan. If it doesn't, stop and flag the mismatch.

3. Implement the plan's steps in order. Follow this codebase's conventions (CLAUDE.md's Key Files index, docs/ARCHITECTURE.md for a module's full detail, existing patterns in the files being touched) rather than introducing new patterns. Match the plan's file list — if implementation reveals the plan missed something material, adjust and note the deviation to the user, don't silently go off-script.

4. Write tests per the plan's testing notes (new API route → integration test happy path + main error case; new Store method → direct or API-level test; bug fix → regression test), following the pattern in `tests/test_integration.py`. Never mock the database.

5. Verify before claiming anything done:
   ```bash
   make test
   ```
   Also run relevant lint/build checks if the plan touched GUI code (`gui/`). Fix failures and re-run — do not report success without a passing run.

6. Commit:
   - Stage only the files relevant to this change (no `git add -A`).
   - Write a commit message explaining why, not just what, per repo convention.
   - Do not use `--no-verify` or `--amend`.

7. Push and open the PR:
   ```bash
   git push -u origin <branch>
   gh pr create --repo alekoHalkias/Emusync --title "..." --body "..."
   ```
   PR body must include `Closes #<issue-number>` so the issue auto-closes on merge, plus a short summary and a test-plan checklist. Do this automatically after the commit — don't ask whether to push or open the PR.

8. Report back the PR URL and a one-line summary of what changed.
