---
name: test-design
description: Generates a detailed test design document from an approved implementation plan to ensure high-quality, validated code changes. Use when the user runs /test-design <issue|PR> after a plan has been approved but before implementation begins.
---

# /test-design - design the tests

Stage 2.5 of 4: issue -> plan -> test-design -> implement -> ship.

## Rules

- No emojis anywhere: test design documents, plan files, commit messages, PR titles/bodies, PR comments.
- The handoff file is the workflow state carrier. Always read it first; never rely on conversation memory.
- The test design must be "lazy" but effective: prioritize high-impact integration tests and root-cause verification over exhaustive unit testing of trivial logic.
- The test design should be a bridge that provides clear guidance for the `/implement` agent.

## Steps

1. Resolve the issue and stage per the `plan` skill's "Resolve" section. Check out the branch. If no handoff file exists, invoke `issue` instead.

2. Read the handoff file at `tools/plans/<N>-handoff.md`. If it does not exist, create it using the template from the `issue` skill, filling in the Issue and Design sections.

3. Read the implementation plan file `tools/plans/<N>-<slug>.md`.

4. Generate a test design in a new file `tools/plans/<N>-test-design.md` with the following structure:
   ```
   ## Test Scope
   <What is being tested and, crucially, what is out of scope.>
   ## Test Types
   - [ ] Integration Tests (e.g., API endpoints, DB migrations)
   - [ ] Unit Tests (e.g., core logic, utility functions)
   - [ ] Regression Tests (e.g., ensuring existing functionality remains intact)
   - [ ] Manual GUI Checks (if applicable)
   ## Test Cases
   ### Happy Path
   - <Scenario> -> <Expected Outcome>
   ### Edge Cases & Error Conditions
   - <Scenario> -> <Expected Outcome>
   ## Affected Existing Tests
   <List of existing tests that might be broken or need updating.>
   ## Implementation Checklist for `/implement`
   - [ ] <Specific testing requirement or verification step to be performed during implementation.>
   ```

5. Update the handoff file. Rewrite section 7 (Test Design) with the test scope, test types, test cases, affected existing tests, and implementation checklist. Update the Metadata section: set `Status: planned`. Append to the Log:
   ```
   - <YYYY-MM-DD> test-design: scope=<summary>, types=<list>
   ```

6. Commit the new test design file, the updated plan file, and the handoff file.

7. Report the test design file path to the user and suggest they proceed with `/implement <N>`.
