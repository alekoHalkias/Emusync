# Handoff: #604 test suite goes over the whole list of tests and is getting big, make the test suite smarter to only test touched files and anything that they interact with

## Metadata
  - Issue: #604
  - Branch: feature/604-test-suite-goes-over-the-whole-list-of-t
  - PR: none
  - Status: implemented
Status: implemented
  - Created: 2026-10-25
  - Last updated: 2026-10-25
  - Fix attempts: 0

## 1. Issue
### Summary
test suite goes over the whole list of tests and is getting big, make the test suite smarter to only test touched files and anything that they interact with

### Motivation
The test suite is large (9100+ lines across 50 files). Running the full suite for small changes is slow and wastes CI/dev time. The current `scripts/test_changed.py` uses naive stem-matching that misses indirect dependencies and cross-module interactions.

### Proposed Behavior / Steps to Reproduce
`scripts/test_changed.py` should intelligently determine which tests to run based on changed files and their dependencies:

1. Map each changed source file to directly related test files (existing stem-matching as baseline).
2. Additionally, trace imports/dependencies from changed files to find downstream modules that may need testing.
3. Include `conftest.py` changes as triggering the full suite (fixtures affect everything).
4. Config files (`.toml`, `.json`, `consoles_data.py`) should trigger relevant integration tests.
5. Gracefully fall back to the full suite when detection is inconclusive.

Steps to reproduce the problem:
1. Make a small change to `server/api/games.py`
2. Run `make test-changed`
3. Observe that only `test_games.py` runs (missing tests that import games.py indirectly)
4. Run the full suite manually to verify nothing is broken

### Affected Area
- `scripts/test_changed.py`
- `Makefile` (test-changed target)
- `tests/` (test discovery)

### Acceptance Criteria
- [ ] Changed `server/api/games.py` runs `test_games.py` and any other tests that import it
- [ ] Changed `server/store/schema.py` runs all store-related tests
- [ ] Changed `tests/conftest.py` triggers the full suite
- [ ] Changed `cli/consoles_data.py` triggers console/memcard/save tests
- [ ] Unrelated test files are not run
- [ ] Fallback to full suite still works when no matches found
- [ ] `make test-changed` works in a clean venv

## 2. Design
### Scope: Tooling/testing only. No server, CLI, or UI changes.
### Backend Changes: Rewrite `scripts/test_changed.py` to use AST-based import graph analysis. Build a reverse dependency map from source files to test files. Add file-type routing for config files, conftest, and CLI/server modules.
### UI Changes: None.
### Sub-issues: none
### Difficulty: 5/10
### Backwards Compatibility: No breaking changes. Pure tooling/testing change. `make test` target unchanged.

## 3. Frontend Plan
### Design Alignment: N/A — no UI changes.
### Visual Pattern: N/A.
### Recommendations: N/A.

## 4. Backend Plan
### Design Alignment: Tooling change only, aligns with CLAUDE.md testing rules (no mocks, real SQLite).
### Backend Pattern: Python script rewrite using AST parsing + file-type routing + transitive dependency resolution.
### Recommendations: Keep stem matching as fallback for edge cases.

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: scripts/test_changed.py (self-test via manual verification)
### Test Cases: See plan steps 5 — 6 scenarios covering API changes, CLI changes, conftest changes, schema changes, switch changes, no changes, and unknown files.
### Edge Cases: conftest.py changes triggering full suite; config file changes; files with no known dependency.
### Integration Points: Makefile test-changed target (no changes needed).

## 7. Test Design
### Test Scope: The test_changed.py script itself — does it select the right tests for each changed-file scenario?
### Test Types: Manual verification by running the script with simulated changes and inspecting output.
### Test Cases: See plan step 5.
### Affected Existing Tests: None — this is a tooling change, no existing tests are modified.
### Implementation Checklist: See plan steps 1-6.

## 8. Implementation Steps
### Steps: Written in plan file.
### Log:
- 2026-10-25 init: handoff created by run-skill.sh

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
- 2026-10-25 init: handoff created by run-skill.sh
- 2026-10-25 issue: workflow initialized, issue body updated with full description
- 2026-10-25 issue: invoking design skill for #604
- 2026-10-25 design: scope=tooling-only, difficulty=5/10, breaking=no
- 2026-10-25 plan: written, awaiting approval
- 2026-10-25 implement: steps 1-6 done — full rewrite of scripts/test_changed.py with AST map, file-type routing, transitive deps, and integration. Verified 6 scenarios.

## Rollback
- **Last known good state:** main
- **Blocked at:** none
- **State at failure:** none
