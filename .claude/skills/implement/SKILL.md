---
name: implement
description: Execute the plan file plans/<issue>-<slug>.md one step at a time, checking off each step in the file as it completes so an interrupted run can resume. Use when the user runs /implement <issue|PR>, after a plan is approved, or when ship has appended fix steps.
---

# /implement - work the plan file

Stage 3 of 4: issue -> plan -> implement -> ship.

## Rules (all stages)

- No emojis anywhere: code comments, plan files, commit messages, PR titles/bodies, PR comments.
- The plan file is the source of truth. Do only what its unchecked steps say.

## Steps

1. Resolve the issue and stage per the `plan` skill's "Resolve" section. Check out the branch. If there is no plan file, invoke `plan` instead. If every step is already checked, invoke `ship`.
   Then set `Status: implementing` in the plan file and commit it. This records plan approval and unlocks the edit hook (`.claude/hooks/require_plan.py`), which blocks edits to repo files outside `plans/` and `.claude/` under any other status.
2. Read the plan file. Find the first unchecked `- [ ]` step. Earlier checked steps are done - do not redo them, but read the code they touched before continuing.
3. For each unchecked step, in order:
   a. Implement exactly that step, following CLAUDE.md conventions and the step's Reuses list.
   b. Verify it: `make lint` for Python, `cd gui && npx tsc --noEmit -p tsconfig.node.json && npx tsc --noEmit -p tsconfig.web.json` for TypeScript, and run the tests closest to the change (`.venv/bin/python -m pytest tests/<file> -v`).
   c. Mark it done in the plan file: `- [ ]` -> `- [x]`. If the step deviated from the plan, add one line under `## Log`: `Step <n>: <what differed and why>`.
   d. Commit the step's files plus the plan file: `git commit -m "#<N> step <n>: <summary>"`. Stage specific paths, never `git add -A`. If the hook demands CLAUDE.md be staged, update CLAUDE.md for real (the plan's Docs step) rather than touching it.
   One commit per step means an interrupted run loses at most the step in progress.
4. If a step cannot be done as written (wrong assumption, missing code), stop, write the blocker under `## Log`, set `Status: blocked`, commit, and report to the user. Do not improvise a different design.
5. When all steps are checked, set `Status: implemented`, commit, and invoke `ship` with the issue number.
