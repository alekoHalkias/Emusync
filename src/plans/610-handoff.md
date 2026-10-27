# Handoff: #610 Restructure project directory layout

## Metadata
- Issue: #610
- Branch: feature/610-restructure-directory-layout
- PR: none
- Status: implementing
- Created: 2025-10-27
- Fix attempts: 0

## 1. Issue
### Summary
Reorganize the project base directory to reduce clutter and improve logical grouping.

### Motivation
The project root has too many directories and files at the top level, making it hard to navigate. Build artifacts, tooling directories, and source code are all mixed together.

### Proposed Behavior / Steps to Reproduce
- Move all source directories under a new `src/` parent: gui/, cli/, server/, tests/, scripts/, docs/, plans/, shared/, emusync.py, emusync
- Consolidate all gitignore build artifacts into a single `.cache/` directory
- Move workflow-cli/ and .skill-runner/ into a `tools/` directory
- Update all path references throughout the codebase

### Affected Area
Entire project structure, all path references (imports, install.sh, Makefile, Electron spawn paths, .gitignore, systemd unit, pyproject.toml)

### Acceptance Criteria
- [ ] All source code under src/
- [ ] Build artifacts under .cache/
- [ ] Tools under tools/
- [ ] No broken imports or path references
- [ ] make dev-server, make dev-gui, make test all work
- [ ] install.sh still functional
- [ ] Electron can still launch the server and GUI
- [ ] .gitignore updated correctly

## 2. Design
### Scope: Large — all directory-level paths in every file
### Backend Changes: All import paths, CLI spawn paths, install.sh, Makefile, systemd unit
### UI Changes: Electron main process spawn paths, preload paths
### Plan Target: fplan (single-pass implementation)
### Sub-issues: none
### Difficulty: medium (many references to update, but straightforward renames)
### Backwards Compatibility: all internal paths change; no external API impact

## 3. Frontend Plan
### Design Alignment: Electron paths updated to src/gui/
### Visual Pattern: N/A
### Recommendations: Update all Electron IPC/spawn paths

## 4. Backend Plan
### Design Alignment: All Python imports, CLI paths, server paths updated
### Backend Pattern: Straightforward rename + path reference updates
### Recommendations: Verify every file that references moved directories

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: tests/test_integration.py (run full suite)
### Test Cases: make test, make dev-server, make dev-gui
### Edge Cases: install.sh path references, systemd service file
### Integration Points: Electron spawn → Python CLI, pip install -e .

## 7. Test Design
### Test Scope: Full test suite, build checks
### Test Types: Integration, build verification
### Test Cases: make test, pip install -e ., make dev-server
### Affected Existing Tests: none (test internals don't change, only paths to find files)
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps:
1. Create src/, .cache/, tools/ directories
2. git mv all source dirs into src/
3. Move build artifacts into .cache/
4. Move tools into tools/
5. Update .gitignore
6. Update install.sh
7. Update Makefile
8. Update systemd service file
9. Update pyproject.toml
10. Update Electron files (runtime.ts, preload.ts, etc.)
11. Update CLAUDE.md
12. Update any other path references
13. pip install -e . and make test

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
- 2025-10-27 issue: workflow initialized
- 2025-10-27 implementing: restructuring directory layout
