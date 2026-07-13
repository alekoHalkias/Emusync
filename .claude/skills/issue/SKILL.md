---
name: issue
description: Wrap up the previous PR and start the next one - prompts for what the new issue should be, checks open GitHub issues for a match, and either adopts one or files a new issue plus its branch. Use when the user runs /issue.
---

# /issue — wrap up, then start the next issue

Follows CLAUDE.md's "Execution approval policy" and "Development workflow" (Steps 1–3) — see those sections for the full approval rules and `gh` setup instructions; not repeated here.

## Steps

1. Verify the previous work is actually done before declaring it done — don't take "merged" on faith:
   ```bash
   git branch --show-current
   gh pr view --json number,state,mergedAt,url 2>/dev/null
   ```
   - If the current branch has an OPEN PR: stop and tell the user "PR #N is still open — merge it, then run /issue again" (include the URL). Do not proceed to ask about a new issue.
   - If there's no PR for this branch (e.g. already on `main`, or the branch was never pushed) or the PR is MERGED: proceed. Output exactly this line:
     > pr merged, make a new issue.

   Then ask the user what the new issue should be about (if `args` already contains a description, use that instead of asking).

2. Check for `gh` (CLAUDE.md's "How Claude agents create issues" has the setup steps if it's missing):
   ```bash
   which gh
   ```
   If missing and no `GITHUB_TOKEN` env var is set, tell the user to run `gh auth login` or set `GITHUB_TOKEN`, then stop.

3. List open issues:
   ```bash
   curl -s "https://api.github.com/repos/alekoHalkias/Emusync/issues?state=open&per_page=50"
   ```
   If one or more open issues look relevant to what the user described, show the candidates (number + title) and ask whether to use one of those instead of filing a new one.
   - If the user picks an existing issue: skip straight to step 5 (branch) using that issue's number/title. Do not create a new issue.
   - If the user says none fit (or there were no candidates), continue to step 4.

4. Draft a title and body for the new issue from the user's description (title: short, imperative; body: what/why + acceptance criteria) and create it automatically, per CLAUDE.md's "How Claude agents create issues" (`gh issue create`, curl fallback with `GITHUB_TOKEN`). Note the returned issue number.

5. Check for overlap, then set up an isolated workspace for the linked branch:
   ```bash
   git fetch --prune && git branch -r
   ```
   If another open branch already touches the same area, warn the user about the overlap in your report, but still proceed — this is informational, not an approval gate.

   Invoke the `superpowers:using-git-worktrees` skill to create `feature/<issue-number>-short-description` in its own isolated worktree rather than switching branches in the current checkout — this is what makes it safe to have several issues in flight without stashing/switching. That skill prefers a native tool (e.g. `EnterWorktree`) when available, falling back to `git worktree add .worktrees/<branch>` otherwise. After the worktree exists, run `bash install.sh` inside it (its own `.venv`/`gui/node_modules` are not shared with the main checkout — they don't exist yet) before treating the workspace as ready. If worktree creation fails (sandbox denial, no `git worktree` support) or the user has declined isolation before, fall back to the plain in-place flow: `git checkout main && git pull && git checkout -b feature/<issue-number>-short-description`.

6. Report back: the issue used or created (number/URL), the branch, and the workspace path (worktree directory, or "in place" if the fallback was used).

7. Invoke the `plan` skill (via the Skill tool) for this issue/branch — do not ask permission first, this is the expected next step in the workflow.
