---
name: github-issue-creator
description: Creates a GitHub issue following the standard EmuSync format (Context, Technical Overview, Affected Components, Acceptance Criteria, Implementation Notes, Testing Plan).
metadata:
  type: project
---

When creating a new GitHub issue, ensure it follows this structure:

## Context
[One or two sentences describing the user story or the 'why' behind this work.]

## Technical Overview
[A summary of the proposed technical approach, including key logic changes, database schema changes, or IPC additions.]

## Affected Components
[A bulleted list of specific files, modules, or UI components that will be modified.]

## Acceptance Criteria
[A checklist of specific, measurable outcomes that must be met to consider the issue 'Done'.]

## Implementation Notes
[Details on specific constraints, configuration requirements, 'gotchas', or design decisions.]

## Testing Plan
[Specific scenarios, test files, or regression tests required to verify the fix/feature.]

# Workflow
1. Define the content for each section.
2. Use `gh issue create --title "<Title>" --body-file <path_to_temp_file>` to create the issue.
3. Ensure the title is descriptive and avoids redundant words.
