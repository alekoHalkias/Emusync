# Handoff: #673 Start fullscreen when launched from Steam

## Metadata
- Issue: #673
- Branch: feature/673-steam-fullscreen
- PR: none
- Status: created
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
### Scope: TBD
### Backend Changes: TBD
### UI Changes: TBD
### Plan Target: TBD (bplan / fplan / both)
### Sub-issues: TBD
### Difficulty: TBD
### Backwards Compatibility: TBD

## 3. Frontend Plan
### Design Alignment: TBD
### Visual Pattern: TBD
### Recommendations: TBD

## 4. Backend Plan
### Design Alignment: TBD
### Backend Pattern: TBD
### Recommendations: TBD

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: TBD
### Test Cases: TBD
### Edge Cases: TBD
### Integration Points: TBD
### Outline: TBD
### Summary: TBD

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps: TBD (written by /plan skills)

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
