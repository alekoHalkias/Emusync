---
name: implement
description: Execute the plan drafted by /plan for the current branch's issue, write tests, run a code-review pass, verify GUI changes actually work end-to-end, commit, push, and open the PR. Use when the user runs /implement, normally right after confirming a /plan.
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

6. **Review the diff before it becomes a PR.** Skip this step for docs-only or config-only changes (nothing to review). Otherwise invoke the `code-review` skill at `low` effort — fast, high-confidence findings only, so routine implementations aren't slowed down chasing speculative issues. If it returns findings:
   - Apply straightforward fixes directly (typo-class bugs, an obviously-missing edge case, a simplification the review calls out).
   - For anything requiring a judgment call (a design tradeoff, an ambiguous edge case, a finding you disagree with), note it in the final report instead of guessing — don't silently drop it either.

7. **Verify GUI changes actually work, not just typecheck.** If the plan touched `gui/` (renderer or electron), invoke the `verify` skill to drive the affected feature end-to-end in the running app before claiming done — per CLAUDE.md's rule that UI changes need to be exercised in a browser, not just type-checked. Skip for CLI/server-only changes with no runtime UI surface.

8. Commit:
   - Stage only the files relevant to this change (no `git add -A`).
   - Write a commit message explaining why, not just what, per repo convention.
   - Do not use `--no-verify` or `--amend`.

9. Push and open the PR:
   ```bash
   git push -u origin <branch>
   gh pr create --repo alekoHalkias/Emusync --title "..." --body "..."
   ```
   PR body must include `Closes #<issue-number>` so the issue auto-closes on merge, plus a short summary and a test-plan checklist. Do this automatically after the commit — don't ask whether to push or open the PR.

10. Report back the PR URL, a one-line summary of what changed, and any judgment-call findings from step 6 that weren't auto-fixed.
