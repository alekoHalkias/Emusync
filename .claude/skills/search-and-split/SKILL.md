---
name: search-and-split
description: Scan the codebase for the largest source files (>=500 lines, top 5), propose them as split candidates with rationale, and — for each one the user approves — file a GitHub issue and run it through the plan/implement/PR pipeline, largest file first, pausing for the user to merge each PR before starting the next. Use when the user runs /search-and-split.
---

# /search-and-split — find oversized files and split the approved ones

Follows CLAUDE.md's "Execution approval policy" and "Development workflow" — issue creation, branching, commits, pushes, and PRs are pre-approved and run without asking. The one deliberate pause point is which files to split (a content decision, not permission) — the per-file merge gate is *verified via `gh`*, not taken on the user's word (step 6e).

## Steps

1. Scan the repo for source file line counts, excluding non-source and generated paths:
   ```bash
   find . \
     \( -path ./node_modules -o -path '*/node_modules' -o -path ./.venv -o -path ./.git \
        -o -path '*/dist' -o -path '*/build' -o -path '*/out' -o -path '*/__pycache__' \
        -o -name '*.egg-info' \) -prune -o \
     -type f \( -name '*.py' -o -name '*.ts' -o -name '*.tsx' -o -name '*.js' -o -name '*.jsx' \) \
     -not -name '*.lock' -not -name '*-lock.json' -not -name '*.tsbuildinfo' \
     -print0 | xargs -0 wc -l | sort -rn
   ```

2. Drop the trailing `total` line, filter to files with **>= 500 lines**, keep the **top 5** by line count.

3. For each candidate, read enough of the file (or lean on docs/ARCHITECTURE.md's Key Files detail, which already documents most large files' responsibilities) to write a one-line rationale — what distinct responsibilities it's mixing, e.g. "owns routing, IPC, and process lifecycle" or "one component handling fetch, layout, and modal state".

4. If no file reaches 500 lines, report that and stop — nothing to split.

5. Present the candidates (path, line count, rationale), largest first, and ask the user via `AskUserQuestion` (multi-select) which ones to turn into split issues. This is a genuine content decision — do not skip it or assume approval.

6. For each approved file, **largest to smallest**:
   a. Draft and create a GitHub issue proposing to split that file into smaller modules (what the file currently does, a sketch of a plausible split, acceptance criteria: behavior unchanged, `make test` passes, docs/ARCHITECTURE.md's Key Files detail updated) — per CLAUDE.md's "How Claude agents create issues".
   b. Check for conflicting branches (`git fetch --prune && git branch -r`) and warn if one already touches the same file, then proceed.
   c. Set up the branch in an isolated worktree, same as `/issue` step 5: invoke `superpowers:using-git-worktrees` for `feature/<issue-number>-split-<short-name>`, then `bash install.sh` inside the new worktree before treating it as ready. Falls back to plain `git checkout main && git pull && git checkout -b ...` if worktree creation isn't available.
   d. Invoke the `plan` skill for that issue, then (once the plan is approved) `implement` — through to a pushed commit and an opened PR, per those skills' normal flow.
   e. Report the PR URL, then **stop** before starting the next approved file — merging takes real time. When the user gives any go-ahead to continue, verify the merge yourself rather than trusting their word:
      ```bash
      gh pr view <PR-number> --json state,mergedAt,url
      ```
      If `state` isn't `MERGED`, report it's still open (with the URL) and don't advance. If merged, proceed to the next file automatically.

7. Once every approved file has been processed (or the user stops early), report a summary: which files got PRs, which are still pending merge.
