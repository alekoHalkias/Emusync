# Handoff: #673 Start fullscreen when launched from Steam

## Metadata
- Issue: #673
- Branch: feature/673-steam-fullscreen
- PR: pending
- Status: shipped
- Created: 2026-11-01
- Fix attempts: 0

## 1. Issue
### Summary
Open the EmuSync GUI in fullscreen when launched from Steam.
### Motivation
display.ts only auto-fullscreens on first run with --fullscreen or SteamDeck/SteamOS env; a Steam shortcut on a normal desktop opens windowed.
### Proposed Behavior / Steps to Reproduce
Detect a Steam-launched process (SteamGameId/SteamAppId env) and start fullscreen.
### Affected Area
src/gui/electron/display.ts, optionally src/gui/electron/steam.ts
### Acceptance Criteria
- Steam launch opens fullscreen
- Desktop launch unchanged
- User can leave fullscreen

## 2. Design
### Scope: ui (Electron main only)
### Backend Changes: none
### UI Changes: display.ts load(): Steam env forces fullscreen for the session, not persisted
### Plan Target: fplan
### Sub-issues: none
### Difficulty: 1/10
### Backwards Compatibility: no breaking changes

## 3. Frontend Plan
### Design Alignment: extends display.ts load() detection
### Visual Pattern: none (no UI change)
### Recommendations: Steam env overrides saved preference for the session, not persisted

## 4. Backend Plan
### Design Alignment: TBD
### Backend Pattern: TBD
### Recommendations: TBD

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: none (manual; no Electron harness)
### Test Cases: manual Steam env vs plain launch
### Edge Cases: saved fullscreen=false with Steam env
### Integration Points: display.ts load -> applyDisplay -> setFullScreen
### Outline
Frontend: 1 force fullscreen on SteamGameId/SteamAppId in display.ts load()
Tests: 2 manual verification + tsc
Docs: 3 none
### Summary: Open the GUI fullscreen when launched from Steam, for that session only.

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps: see tools/plans/673-steam-fullscreen.md
1. Force fullscreen on SteamGameId/SteamAppId. Files: src/gui/electron/display.ts. Reuses: --fullscreen condition. New: none.
2. Tests: manual (no Electron test harness). Files: none.
3. Docs: none.

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
- 2026-11-01 design: scope=ui, plan_target=fplan, difficulty=1/10, breaking=no
- 2026-11-01 fplan: 3 steps written, visual_pattern=none
- 2026-11-01 tplan: test_file=none (manual), 2 test cases defined
- 2026-11-01 implement: steps 1-3 done (SteamGameId/SteamAppId force fullscreen in display.ts)
