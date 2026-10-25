# Issue Skill

Create a new GitHub issue describing the bug or feature.

## Goal

Write a clear, actionable issue with:
- Title: concise, specific, no emojis
- Description: context, symptoms, expected behavior
- Steps to reproduce (if applicable)
- Acceptance criteria
- Labels: bug, enhancement, or appropriate tag
- Assign to self (or unassigned)
- Milestone if applicable

## Actions

1. Read the project's CLAUDE.md and docs/GOTCHAS.md for context
2. Create the issue using the `gh` action:
   ```
   gh issue create --title "..." --body "..." --label "..."
   ```
3. Update the handoff file: set Status to `created`, fill Section 1 (Issue) and Section 2 (Design)
4. Append to log: `YYYY-MM-DD issue: <description>`

## Output

The issue number and URL.
