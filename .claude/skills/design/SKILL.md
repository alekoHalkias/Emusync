---
name: design
description: Analyze an issue to split it into UI/Backend parts and potential sub-issues, then append difficulty to the GitHub issue and update the handoff file.
---

# /design - analyze and decompose

Stage 1.5 of 4: issue -> design -> plan -> implement -> ship.

## Rules (all stages)

- No emojis anywhere: issue titles/bodies, plan files, commit messages, PR titles/bodies, PR comments.
- Professional, plain tone. No filler, no marketing language.
- The handoff file is the workflow state carrier. Always read it first; never rely on conversation memory.

## Resolve (shared by all four skills)

Input is an issue number or a PR number.
- PR number: `gh pr view <N> --repo alekoHalkias/Emusync --json body,headRefName,state` and read the issue from `Closes #X`.
- Issue number: `git fetch --prune`, then find the branch with `git branch -a --list "*/<N>-*"` and the handoff at `plans/<N>-handoff.md` on that branch.

Stage:
| State | Next skill |
|---|---|
| No branch or no handoff file | design |
| Design complete (Plan target set) | bplan / fplan / both (see step 9) |
| Plan has unchecked `- [ ]` steps (`Status: planned` = awaiting approval) | implement |
| All steps checked, `PR: none` | ship |
| `PR: #M` and status `shipped` | done - report it |
| `Status: blocked` | stop, show the failure report |

If invoked at the wrong stage, say so and invoke the right skill.

## Steps

1. Resolve the issue number. `gh issue view <N> --repo alekoHalkias/Emusync --json number,title,body,comments` and read all of it.

2. Read the handoff file at `plans/<N>-handoff.md`. If it does not exist, create it using the template from the `issue` skill, filling in the Issue section from what you just read.

3. Analyze the scope.
   - Identify **Backend changes**: Python/FastAPI, SQLite/Store, CLI, mDNS, etc.
   - Identify **UI changes**: Electron main, React components, IPC channels, `emusync.d.ts`.

4. Backwards compatibility check (run before decomposition).
   For each changed area, verify:
   - **Schema changes**: If new columns/tables, does `from_version < N` exist in `_migrate()`? Is `_SCHEMA_VERSION` bumped? Is the fresh-DB `user_version` stamp updated? If a schema change is breaking (removes a column that old clients might reference), flag it.
   - **API changes**: Are old endpoint signatures still supported? If an endpoint parameter is removed or renamed, is there a transitional path?
   - **Config changes**: Are old `emusync.toml` keys still read? If a config key is renamed or removed, old configs will silently break — flag it.
   - **IPC changes**: Are old `ipcMain.handle` / `ipcRenderer.invoke` channels still handled? If an IPC channel is removed or its signature changes, the renderer's `emusync.d.ts` type contract is broken for any still-running Electron instance.
   - **Store method changes**: Do old store method signatures still work? `store.get_game(slug)` callers must not break.
   - **Console detection**: If `consoles_data.py` entries change, old paired devices may misidentify consoles.
   If any breaking change is detected, add +2 to the difficulty rating (see step 6).

5. Decomposition:
   - Can the issue be split into sub-issues (e.g., a backend-only API addition vs. the UI that uses it)?
   - If yes, list the proposed sub-issues with brief summaries.

6. Difficulty assessment:
   - Evaluate the complexity on a scale of 1 to 10.
   - Consider: number of files, schema changes, IPC complexity, UI/UX design, risk of regression.
   - If the backwards compatibility check (step 4) flagged any breaking changes, add +2 to the difficulty. Breaking changes that affect existing paired devices or running Electron instances are especially risky.

7. Update GitHub:
   - Append a standardized difficulty block to the bottom of the issue:
     ```
     ---
     ## Design Analysis
     - **Backend:** <summary of changes>
     - **UI:** <summary of changes>
     - **Plan target:** bplan / fplan / both (which plan skill to invoke)
     - **Sub-issues:** <list of proposed sub-issues, or "none">
     - **Difficulty:** <N>/10
     ## Backwards Compatibility
     - **Breaking:** yes/no
     - **Details:** <summary of any breaking changes, or "none">
     ```

8. Update the handoff file. Rewrite section 2 (Design) with the analysis results, including a `Plan target` field stating which plan skill(s) to invoke: `bplan`, `fplan`, or `both`. Update the Metadata section: set `Status: designed`. Append to the Log:
   ```
   - <YYYY-MM-DD> design: scope=<backend+ui>, plan_target=<bplan|fplan|both>, difficulty=<N>/10, breaking=<yes/no>
   ```

9. Report the analysis to the user and invoke the appropriate plan skill(s):
   - **Backend only** (`Plan target: bplan`): invoke `bplan` with the issue number. On completion, invoke `tplan`.
   - **Frontend only** (`Plan target: fplan`): invoke `fplan` with the issue number. On completion, invoke `tplan`.
   - **Both sides** (`Plan target: both`): invoke `bplan` first, then `fplan`. After both plan files are written and committed, invoke `merge` to reconcile them. On merge completion, invoke `tplan`.
