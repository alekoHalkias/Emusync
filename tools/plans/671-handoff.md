# Handoff: #671 Fix games not launching from EmuSync

## Metadata
- Issue: #671
- Branch: feature/671-fix-game-launch
- PR: pending
- Status: implementing
- Created: 2026-11-01
- Fix attempts: 0

## 1. Issue
### Summary
Launching a game from EmuSync no longer starts the game.
### Motivation
Core function broken.
### Proposed Behavior / Steps to Reproduce
Press Play on a configured game in the GUI; the game does not start.
### Affected Area
src/gui/electron/game.ts (game:launch), src/cli/run.py
### Acceptance Criteria
- Root cause identified, regression test added
- Local and network ROM games launch

## 2. Design
### Scope: backend (root cause not yet identified)
### Backend Changes: trace src/cli/run.py launch path; fix at origin of failure; add regression test
### UI Changes: none expected (game.ts spawns CLI with stdio ignored; errors are invisible)
### Plan Target: bplan
### Sub-issues: none
### Difficulty: 3/10
### Backwards Compatibility: no breaking changes

## 3. Frontend Plan
### Design Alignment: TBD
### Visual Pattern: TBD
### Recommendations: TBD

## 4. Backend Plan
### Design Alignment: fix stays in cli/run.py launch path
### Backend Pattern: reuse _resolve_launch_command / resolve_rom_path
### Recommendations: reproduce first; root cause unknown

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: src/tests/test_run_reconcile.py
### Test Cases: regression for reproduced launch failure
### Edge Cases: network ROM live vs localized; %ROM% vs legacy path
### Integration Points: _resolve_launch_command -> shlex.split -> _launch_and_wait
### Outline
Backend: 1 reproduce via CLI; 2 fix cause in run.py launch path
Tests: 3 regression test in test_run_reconcile.py
Docs: 4 none
### Summary: Find and fix why emusync run no longer starts the emulator, with a regression test.

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps: see tools/plans/671-fix-game-launch.md
1. Reproduce via CLI. Files: none. Reuses: CLI. New: none.
2. Fix cause at origin. Files: src/cli/run.py or store (TBD). Reuses: _resolve_launch_command. New: none.
3. Regression test. Files: src/tests/. Reuses: client fixture, real SQLite.
4. Docs: none.

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
- 2026-11-01 issue: workflow initialized
- 2026-11-01 design: scope=backend, plan_target=bplan, difficulty=3/10, breaking=no
- 2026-11-01 bplan: 4 steps written, backend_pattern=reproduce then fix in run.py launch path
- 2026-11-01 tplan: test_file=src/tests/test_run_reconcile.py, 1 test case defined
- 2026-11-01 implement: steps 1-2 done (wrapper venv lookup, GUI launch.log)
- 2026-11-01 implement: steps 3-4 done (wrapper regression test; docs none needed)
- 2026-11-01 implement: F1.1 SCRIPT path in runtime.ts (real root cause of GUI+Steam)
