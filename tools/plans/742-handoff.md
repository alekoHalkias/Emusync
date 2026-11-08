# Handoff: #742 Save push is killed when a Steam-launched game is stopped from the GUI

## Metadata
- Issue: #742
- Branch: feature/742-steam-stop-push-killed
- PR: none
- Status: implementing
- Created: 2026-11-08
- Fix attempts: 0

## 1. Issue
### Summary
Stopping a Steam-launched game from the GUI ends `emusync run` before the post-game push completes.
### Motivation
Save is not uploaded to the server.
### Proposed Behavior / Steps to Reproduce
Launch from Steam, close from the EmuSync GUI, check the server.
### Affected Area
src/gui/electron/game.ts (game:stop-external), src/cli/run_offline.py (_detach_after_game), src/cli/run.py
### Acceptance Criteria
- Push and lock release complete after GUI stop.
- Push survives Steam ending the process tree/cgroup (systemd-run --user --scope where available, fork fallback).
- Regression test.

## 2. Design
### Scope: backend
### Backend Changes: run_offline._detach_after_game escapes Steam's scope (systemd transient scope if available, fork fallback); check game:stop-external does not signal the detached child.
### UI Changes: none expected
### Plan Target: bplan
### Sub-issues: none
### Difficulty: 5/10
### Backwards Compatibility: no breaking changes

## 4. Backend Plan
### Design Alignment: extends #725 _detach_after_game; best-effort with silent fallback
### Backend Pattern: optional OS helper, swallow failures
### Recommendations: none

## 6. Testing Plan
### Test File: src/tests/test_run_detach.py
### Test Cases: no_busctl no-op; cgroup changes (skipif no user bus); existing fork test
### Edge Cases: busctl present, bus unreachable
### Integration Points: _detach_after_game child path
### Outline
Backend: 1 add _escape_steam_scope + call in detach child; 3 docs (GOTCHAS, CLAUDE.md)
Tests: 2 extend test_run_detach.py (reuses its subprocess fork pattern, no new infra)
### Summary: Detached post-game push moves itself into a systemd user scope so Steam's teardown cannot kill it.

## 8. Implementation Steps
- Plan file: tools/plans/742-steam-stop-push-killed.md (3 steps)
- Step 1: touches run_offline.py; reuses _detach_after_game; new _escape_steam_scope (nothing talks to systemd)
- Step 2: touches test_run_detach.py; reuses its subprocess fork pattern
- Step 3: touches GOTCHAS.md, CLAUDE.md; reuses #725 text

## 12. Log
- 2026-11-08 issue: workflow initialized
- 2026-11-08 design: scope=backend, plan_target=bplan, difficulty=5/10, breaking=no
- 2026-11-08 bplan: 3 steps written, backend_pattern=best-effort systemd scope escape in detach child
- 2026-11-08 tplan: test_file=src/tests/test_run_detach.py, 3 test cases defined
