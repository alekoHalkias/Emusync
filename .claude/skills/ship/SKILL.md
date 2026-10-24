---
name: ship
description: Run the test suite for a fully implemented plan; on pass, push and open (or update) a PR that closes the issue and sync the server PC; on failure, loop back through plan and implement on the same branch and PR, stopping after 3 consecutive failures with a root-cause report. Use when the user runs /ship <issue|PR> or after implement finishes.
---

# /ship - test, PR, or fix loop

Stage 4 of 4: issue -> plan -> implement -> ship.

## Rules (all stages)

- No emojis anywhere: commit messages, PR titles/bodies, PR comments, plan files, failure reports.
- The handoff file is the workflow state carrier. Always read and update it.
- Never create a new issue or a second PR for test failures. Fixes go on the same branch and PR.
- Never use `--no-verify`, `--force`, or `--amend`.

## Steps

1. Resolve the issue and stage per the `plan` skill's "Resolve" section. Check out the branch and read the handoff file at `plans/<N>-handoff.md`. If any plan step is unchecked, invoke `implement` instead.

2. Run tests: `make test-changed`, then `make test`. Capture the output.

3. On pass:
   a. Set `Fix attempts: 0` and `Status: shipped` in the handoff file.
   b. If `PR: none`: `git push -u origin <branch>`, then
      `gh pr create --repo alekoHalkias/Emusync --base main --title "<title>" --body-file <file>`.
      Body:
      ```
      ## Summary
      <what changed and why, 2-5 sentences>

      ## Changes
      - <file or area>: <change>

      ## Testing
      - <tests added/run, result>

      Closes #<N>
      ```
      Write `PR: #<M>` into the handoff file, commit, push.
      If `PR: #<M>` already exists: just commit and push; the PR updates itself. Add a short PR comment summarizing the fix if this was a fix loop.
   c. Run code review: invoke `review` on the branch diff against `main`.
      - If any finding has category `gotcha-violation` or `correctness`, block ship. Report findings to user, set `Status: implementing` in the handoff file, and re-invoke `implement` for fixes. Commit the fix, push, and re-run ship from step 2.
      - If findings are only `docs-stale`, `test-gap`, or `style`, note them in a PR comment but continue to the next step.
   d. Check mergeability: `gh pr view <M> --json mergeable`. If conflicting and trivial, set `Status: implementing` (the edit hook requires it), merge `origin/main`, resolve, then set `Status: shipped` again and commit; otherwise report it.
   e. Sync the server PC (standing instruction):
      `ssh -o BatchMode=yes server@192.168.4.111 'cd ~/Github/Emusync && git fetch -q --prune && git checkout <branch> && git pull -q; systemctl --user restart emusync-server && sleep 4 && curl -s localhost:8765/health'`
      Leave any uncommitted change on the server alone; report checkout failures instead of discarding.
      Update the handoff file: set section 10 (Ship) `Server Sync: done` or `failed`. Append to the Log:
      ```
      - <YYYY-MM-DD> ship: server sync <done/failed>
      ```
   f. Run documentation sync: invoke `docs` on the branch diff against `main` to update ARCHITECTURE.md, GOTCHAS.md, and CLAUDE.md.
      - Commit doc updates to the same branch (they appear in the same PR).
      - Use `git add` with specific paths, never `git add -A`.
      - Push the doc updates to the PR branch.
      - Report which files were updated and what changed in each.
      Update the handoff file: set section 10 (Ship) `Doc Sync: done`. Append to the Log:
      ```
      - <YYYY-MM-DD> ship: doc sync updated ARCHITECTURE.md, GOTCHAS.md, CLAUDE.md
      ```
   g. Report the PR URL and a one-line summary.

4. On failure:
   a. Identify the failure from the output: test id, error, and the code it points at. Read that code. Do not guess from the test name alone.
   b. Increment `Fix attempts` in the handoff file and commit.
   c. If `Fix attempts` is now 4 (three consecutive fix loops already failed), go to step 5.
   d. Otherwise invoke `plan` in fix-plan mode with the failure details. It appends fix steps and invokes `implement`, which invokes `ship` again.

5. Stop after three consecutive failed fix loops. Write `## Failure report` into the handoff file and the plan file, and post the same text as a PR comment (push the branch and open the PR as a draft first if none exists, with `Closes #<N>`):
   ```
   ## Failure report
   Fix loop stopped after 3 consecutive failed attempts.

   ### <test id>
   Error: <message>
   Attempts: <what each fix tried>
   Likely root cause: <best analysis, with file:line>
   ```
   Set `Status: blocked` in the handoff file, commit, push, and report to the user. Do not continue.
