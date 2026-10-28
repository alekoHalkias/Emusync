---
name: implement
description: Execute the plan file tools/plans/<issue>-<slug>.md one step at a time, checking off each step in the file as it completes so an interrupted run can resume. Use when the user runs /implement <issue|PR>, after a plan is approved, or when ship has appended fix steps.
---

# /implement - work the plan file

Stage 3 of 4: issue -> plan -> implement -> ship.

## Rules (all stages)

- No emojis anywhere: code comments, plan files, commit messages, PR titles/bodies, PR comments.
- The handoff file is the workflow state carrier. Always read it first; never rely on conversation memory.
- The plan file is the source of truth. Do only what its unchecked steps say.

## Steps

1. Resolve the issue and stage per the `plan` skill's "Resolve" section. Check out the branch. If there is no handoff file, invoke `issue` instead. If every step is already checked, invoke `ship`.
   Then set `Status: implementing` in the handoff file and commit it. This records plan approval and unlocks the edit hook (`.claude/hooks/require_plan.py`), which blocks edits to repo files outside `tools/plans/` and `.claude/` under any other status.

2. Read the handoff file at `tools/plans/<N>-handoff.md` and the plan file at `tools/plans/<N>-<slug>.md`. Find the first unchecked `- [ ]` step. Earlier checked steps are done - do not redo them, but read the code they touched before continuing.

3. For each unchecked step, in order:
   a. Implement exactly that step, following CLAUDE.md conventions and the step's Reuses list.
   b. Verify it: `make lint` for Python, `cd src/gui && npx tsc --noEmit -p tsconfig.node.json && npx tsc --noEmit -p tsconfig.web.json` for TypeScript, and run the tests closest to the change (`.cache/.venv/bin/python -m pytest src/tests/<file> -v`).
   c. Mark it done in the plan file: `- [ ]` -> `- [x]`. If the step deviated from the plan, add one line under `## Log` in the plan file: `Step <n>: <what differed and why>`.
   d. Update the handoff file. In section 8 (Implementation Steps), mark step <n> as done and append any deviation to its Log line. Update the Metadata section: set `Status: implementing`. Append to the Log:
      ```
      - <YYYY-MM-DD> implement: step <n> done (<one-line summary>)
      ```
   e. Commit the step's files plus the plan file and handoff file: `git commit -m "#<N> step <n>: <summary>"`. Stage specific paths, never `git add -A`. If the hook demands CLAUDE.md be staged, update CLAUDE.md for real (the plan's Docs step) rather than touching it.

   One commit per step means an interrupted run loses at most the step in progress.

4. If a step cannot be done as written (wrong assumption, missing code), stop, write the blocker under `## Log` in the handoff file, set `Status: blocked`, commit, and report to the user. Do not improvise a different design.
   a. **Record the rollback state.** Note the current git commit hash (`git rev-parse HEAD`) and the plan step number. Append a `## Rollback` section to the handoff file:
      ```
      ## Rollback
      - **Last known good state:** commit `<hash>` before step `<n>`
      - **Blocked at:** step `<n>` — `<one-line blocker summary>`
      - **State at failure:** `git diff <hash>..HEAD --stat`
      ```
   b. **Offer rollback vs. fix.** Present both options to the user:
      - **Rollback:** `git reset --hard <hash>` to restore the repo to the last known good state before this step. The plan retains the blocker for later review.
      - **Fix:** Keep the current state and invoke `plan` in fix-plan mode to generate a fix plan on top of the broken state.
      Default to rollback if the user does not respond within a reasonable time, or if the blocker is a fundamental design error (not a test bug or minor adjustment).

5. When all steps are checked, set `Status: implemented` in the handoff file, commit, and invoke `ship` with the issue number.
