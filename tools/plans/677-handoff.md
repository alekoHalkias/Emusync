# Handoff: #677 Let the AppImage add Steam shortcuts without EMUSYNC_SCRIPT

## Metadata
- Issue: #677
- Branch: feature/677-appimage-steam-launcher
- PR: none
- Status: planned
- Created: 2026-11-01
- Fix attempts: 0

## 1. Issue
### Summary
AppImage v0.8.6 refuses Steam add with an EMUSYNC_SCRIPT error (#676 guard).
### Motivation
Users should not need an env var.
### Proposed Behavior / Steps to Reproduce
Run AppImage with EMUSYNC_SCRIPT unset; add a game to Steam.
### Affected Area
src/gui/electron/runtime.ts, steam.ts, game.ts, server.ts, paths.ts; src/gui/package.json build config
### Acceptance Criteria
- Add to Steam works without EMUSYNC_SCRIPT
- Target survives restart and updates
- Error is actionable in the GUI
- Dev checkout unchanged

## 2. Design
### Scope: electron main only
### Backend Changes: none
### UI Changes: launcher resolution order EMUSYNC_SCRIPT > display.json repoPath > common checkout dirs; addGame opens folder picker when none found, validates src/emusync, persists
### Plan Target: fplan
### Sub-issues: none
### Difficulty: 4/10
### Backwards Compatibility: not breaking

## 3. Frontend Plan
### Design Alignment: no new UI; native folder dialog pattern from files.ts
### Visual Pattern: none
### Recommendations: none

## 4. Backend Plan
### Design Alignment: TBD
### Backend Pattern: TBD
### Recommendations: TBD

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: none (no TS harness; manual)
### Test Cases: manual: picker on first add and persisted repoPath; no picker on second add; cancel leaves vdf unchanged
### Edge Cases: invalid pick rejected; stale repoPath skipped; dev/EMUSYNC_SCRIPT unchanged; save({...load()}) preserves repoPath
### Integration Points: tsc both configs; make test-changed
### Outline
Frontend (electron): 1 display.ts repoPath; 2 launcher.ts findLauncher/pickLauncher; 3 steam.ts + game.ts use them; 5 CLAUDE.md.
Tests: 4 manual + tsc.
### Summary: Add-to-Steam from the AppImage finds or asks for a repo checkout and remembers it, so no env var is needed.

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps
1. display.ts: add optional repoPath (reuses load/save).
2. launcher.ts (new; display.ts<->runtime.ts import cycle): findLauncher() and pickLauncher().
3. steam.ts + game.ts: use findLauncher() ?? pickLauncher(); drop LAUNCHER_STABLE guard; readers fall back to LAUNCHER.
4. Tests: manual + tsc.
5. Docs: CLAUDE.md rule update.

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
- 2026-11-01 design: scope=ui, plan_target=fplan, difficulty=4/10, breaking=no
- 2026-11-01 fplan: 5 steps written, visual_pattern=none
- 2026-11-01 tplan: test_file=none, 3 manual cases defined
