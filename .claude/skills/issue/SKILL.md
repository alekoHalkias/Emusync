---
name: issue
description: Turn a feature idea or bug description into a professionally formatted GitHub issue on alekoHalkias/Emusync, then hand off to the design skill. Use when the user runs /issue or describes a feature/bug they want filed. Also accepts an issue or PR number to resume the workflow at whatever stage it is in.
---

# /issue - file the issue

Stage 1 of 4: issue -> plan -> implement -> ship.

## Rules (all stages)

- No emojis anywhere: issue titles/bodies, plan files, commit messages, PR titles/bodies, PR comments.
- Professional, plain tone. No filler, no marketing language.
- The handoff file is the workflow state carrier. Always read it first if it exists; never rely on conversation memory.

## Resume mode

If args are a number (`123`, `#123`, or `PR 45`) instead of a description, do not file anything. Resolve the stage as described in the `design` skill's "Resolve" section and invoke the skill for that stage.

## Steps

1. If no description was given, ask the user what the feature or bug is.
2. Check for duplicates: `gh issue list --repo alekoHalkias/Emusync --state open --limit 100 --search "<keywords>"`. If one matches, show it and ask whether to use it instead; if yes, skip to step 5 with that number.
3. Read enough code to name the affected area accurately (module/file names, not a full plan). Do not design the solution here.
4. Write the body to a temp file in the scratchpad and create the issue:
   `gh issue create --repo alekoHalkias/Emusync --title "<title>" --body-file <file> --label <enhancement|bug>`
   (drop `--label` if the label does not exist). Title: short, imperative, no prefix tags.

   Feature body:
   ```
   ## Summary
   ## Motivation
   ## Proposed Behavior
   ## Affected Area
   ## Acceptance Criteria
   - [ ] ...
   ```
   Bug body:
   ```
   ## Summary
   ## Steps to Reproduce
   ## Expected Behavior
   ## Actual Behavior
   ## Affected Area
   ## Acceptance Criteria
   - [ ] ...
   ```

5. Branch. If no `*/<N>-*` branch exists: `git fetch --prune && git checkout main && git pull && git checkout -b feature/<N>-<slug>`. If it exists, check it out. Never work on `main`.

6. Create or read the handoff file at `tools/plans/<N>-handoff.md`. If it does not exist, write it with the template below. If it exists, read it and fill in the Issue section (sections 1-2).

   Handoff template (write only if the file does not exist):
   ```
   # Handoff: #<N> <title>

   ## Metadata
   - Issue: #<N>
   - Branch: feature/<N>-<slug>
   - PR: none
   - Status: created
   - Created: <YYYY-MM-DD>
   - Fix attempts: 0

   ## 1. Issue
   ### Summary
   ### Motivation
   ### Proposed Behavior / Steps to Reproduce
   ### Affected Area
   ### Acceptance Criteria

   ## 2. Design
   ### Scope: TBD
   ### Backend Changes: TBD
   ### UI Changes: TBD
   ### Plan Target: TBD (bplan / fplan / both)
   ### Sub-issues: TBD
   ### Difficulty: TBD
   ### Backwards Compatibility: TBD

   ## 3. Frontend Plan
   ### Design Alignment: TBD
   ### Visual Pattern: TBD
   ### Recommendations: TBD

   ## 4. Backend Plan
   ### Design Alignment: TBD
   ### Backend Pattern: TBD
   ### Recommendations: TBD

   ## 5. Merged Plan
   ### Conflicts Resolved: none
   ### Unresolved Conflicts: none

   ## 6. Testing Plan
   ### Test File: TBD
   ### Test Cases: TBD
   ### Edge Cases: TBD
   ### Integration Points: TBD

   ## 7. Test Design
   ### Test Scope: TBD
   ### Test Types: TBD
   ### Test Cases: TBD
   ### Affected Existing Tests: TBD
   ### Implementation Checklist: TBD

   ## 8. Implementation Steps
   ### Steps: TBD (written by /plan skills)

   ## 9. Review
   ### Findings: TBD
   ### Blocked: TBD
   ### Blockers: TBD

   ## 10. Ship
   ### Status: pending
   ### PR: none
   ### Server Sync: pending
   ### Doc Sync: pending

   ## 11. Fix Attempts
   ### Attempt 1: none
   ### Attempt 2: none
   ### Attempt 3: none

   ## 12. Log
   - <YYYY-MM-DD> issue: workflow initialized
   ```

7. Report the issue number and URL, then invoke the `design` skill with the issue number.
