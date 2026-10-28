---
name: cleanup
description: Clean up plan/handoff files and prune the feature branch after a PR is merged or closed on the repo. Use when the user runs /cleanup or after ship confirms a PR has been merged/closed.
---

# /cleanup - post-merge/closure cleanup

Runs after a PR is merged or closed. Cleans up the plan files, handoff, and prunes the feature branch.

## Rules

- No emojis.
- Always confirm the PR state on GitHub before cleaning up anything.
- Never delete files or prune branches for issues that are still open.

## Steps

1. Resolve the issue number. If args are a number (`123`, `#123`, or `PR 45`), use it. Otherwise ask the user.

2. Check the PR state: `gh pr list --repo alekoHalkias/Emusync --state all --search "Closes #<N>"`. If no PR exists, check `gh issue view <N> --repo alekoHalkias/Emusync --json state` to confirm it is closed (merged or otherwise). If the issue/PR is still open, stop and report: "Issue #N is still open; do not clean up."

3. If the PR is merged or the issue is closed, confirm with the user (one-line: "PR #M merged — proceeding with cleanup.").

4. Read the handoff file at `tools/plans/<N>-handoff.md`. Append to the Log section:
   ```
   - <YYYY-MM-DD> cleanup: workflow closed
   ```
   Set `Status: closed` in the Metadata section. Commit and push the handoff update.

5. Find the plan file(s) for this issue: `tools/plans/<N>-*.md` (the handoff plus any `<N>-<slug>.md` plan files). Delete all matching plan files (not the handoff — that was already updated in step 4, so delete the handoff too after the log update).

6. Get the branch name from the handoff file's `Branch:` line. Prune it:
   - Remote: `git push origin --delete <branch>`
   - Local: `git branch -d <branch>`
   If the local branch has unmerged commits, use `-D` instead and note it.

7. Report: "Cleaned up issue #N — removed plan files, pruned branch `<branch>`."
