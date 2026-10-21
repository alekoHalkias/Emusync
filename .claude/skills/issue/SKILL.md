---
name: issue
description: Turn a feature idea or bug description into a professionally formatted GitHub issue on alekoHalkias/Emusync, then hand off to the plan skill. Use when the user runs /issue or describes a feature/bug they want filed. Also accepts an issue or PR number to resume the workflow at whatever stage it is in.
---

# /issue - file the issue

Stage 1 of 4: issue -> plan -> implement -> ship.

## Rules (all stages)

- No emojis anywhere: issue titles/bodies, plan files, commit messages, PR titles/bodies, PR comments.
- Professional, plain tone. No filler, no marketing language.

## Resume mode

If args are a number (`123`, `#123`, or `PR 45`) instead of a description, do not file anything. Resolve the stage as described in the `plan` skill's "Resolve" section and invoke the skill for that stage.

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
5. Report the issue number and URL, then invoke the `plan` skill with the issue number.
