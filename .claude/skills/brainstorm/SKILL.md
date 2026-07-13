---
name: brainstorm
description: Read the whole codebase, surface the top 5 biggest features/fixes worth doing, file an approved issue for each, then work the list one issue at a time (plan → implement → PR), pausing for user PR approval before starting the next. Use when the user runs /brainstorm.
---

# /brainstorm — find the biggest wins, then work the backlog

Follows CLAUDE.md's "Execution approval policy" and "Development workflow". Issue/branch/commit/push/PR creation are pre-approved per that policy — the one deliberate human checkpoint in this skill is approving which of the 5 candidates become issues. The PR-merge gate between backlog items is *verified*, not taken on the user's word — see step 5e.

## Steps

1. **Survey the codebase.** Spawn an `Explore` agent (or `general-purpose` if synthesis/judgment is needed beyond location-finding) with "very thorough" breadth to read across `cli/`, `server/`, `gui/electron/`, `gui/renderer/src/`, and `tests/`. Ask it to report candidate biggest-impact features or fixes with file/line evidence — not vague suggestions. In parallel, pull current open issues so candidates don't duplicate existing work:
   ```bash
   curl -s "https://api.github.com/repos/alekoHalkias/Emusync/issues?state=open&per_page=50"
   ```

2. **Pick the top 5.** From the survey, select the 5 highest-impact, non-duplicate items. For each, draft a title and a short body (what/why + acceptance criteria, matching the `issue` skill's format). Bias toward things that are concretely scoped (a real bug, a missing capability referenced in CLAUDE.md gotchas/TODOs, an inconsistency between mirrored code paths) over vague polish.

3. **Get approval before filing anything.** Present all 5 candidates (title + one-line rationale each) to the user in one shot via `AskUserQuestion` (multiSelect) — let them approve some, all, or none, and edit/reject individual ones via free text. Do not create any issue before this checkpoint; this is the one required pause before touching GitHub.

4. **File the approved issues in parallel.** For each approved candidate, create the GitHub issue per CLAUDE.md's "How Claude agents create issues" (`gh issue create`, curl fallback with `GITHUB_TOKEN`). Fire these as parallel tool calls in a single message — they're independent. Collect the resulting issue numbers in the order presented; this ordered list is the backlog for step 5.

5. **Work the backlog one issue at a time.** For each issue number in order:
   a. Check for conflicting branches (`git fetch --prune && git branch -r`); warn if another branch already touches the same area, but proceed.
   b. Set up the branch in an isolated worktree, same as `/issue` step 5: invoke `superpowers:using-git-worktrees` for `feature/<issue-number>-short-description`, then `bash install.sh` inside the new worktree before treating it as ready. Falls back to plain `git checkout main && git pull && git checkout -b ...` if worktree creation isn't available.
   c. Invoke the `plan` skill for this issue. It will read the issue, ask any genuinely-open clarifying questions, and present a plan — resolve those inline so the loop doesn't stall on a silent wait.
   d. Once the plan is approved (by you resolving its clarifying questions and confirming, or immediately if it had none needing input), invoke the `implement` skill to build it, test it, commit, push, and open the PR.
   e. **Stop after the PR is opened.** Don't advance to the next issue on the spot — merging takes real time (review, CI, a manual click). When the user gives any go-ahead to continue (e.g. "next", "continue", or just re-invoking), verify the merge yourself rather than trusting their word:
      ```bash
      gh pr view <PR-number> --json state,mergedAt,url
      ```
      If `state` isn't `MERGED`, report that it's still open (with the URL) and don't advance. If it's merged, proceed to the next issue automatically — no further confirmation needed.
   f. On a verified merge, move to the next issue in the backlog. Report a one-line status each time you advance ("issue #N done, PR #M merged — starting issue #N+1").

6. When the backlog is empty, report a final summary: all 5 issues, their PR links, and merge status as of the last confirmation.
