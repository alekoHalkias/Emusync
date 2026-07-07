---
name: issue
description: Wrap up the previous PR and start the next one - prompts for what the new issue should be, checks open GitHub issues for a match, and either adopts one or files a new issue plus its branch. Use when the user runs /issue.
---

# /issue — wrap up, then start the next issue

Follows CLAUDE.md's "Execution approval policy" and "Development workflow" (Steps 1–3) — see those sections for the full approval rules and `gh` setup instructions; not repeated here.

## Steps

1. Output exactly this line first, nothing else:
   > pr merged, make a new issue.

   Then ask the user what the new issue should be about (if `args` already contains a description, use that instead of asking).

2. Check for `gh` (CLAUDE.md's "How Claude agents create issues" has the setup steps if it's missing):
   ```bash
   export PATH="$HOME/.local/bin:$PATH"
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

5. Create and check out the linked branch (CLAUDE.md Step 2/3):
   ```bash
   git fetch --prune && git branch -r
   ```
   If another open branch already touches the same area, warn the user about the overlap in your report, but still proceed — this is informational, not an approval gate.
   ```bash
   git checkout main && git pull && git checkout -b feature/<issue-number>-short-description
   ```

6. Report back: the issue used or created (number/URL) and the branch now checked out.

7. Invoke the `plan` skill (via the Skill tool) for this issue/branch — do not ask permission first, this is the expected next step in the workflow.
