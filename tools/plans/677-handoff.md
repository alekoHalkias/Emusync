# Handoff: #677 Let the AppImage add Steam shortcuts without EMUSYNC_SCRIPT

## Metadata
- Issue: #677
- Branch: feature/677-appimage-steam-launcher
- PR: none
- Status: designed
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
- 2026-11-01 design: scope=ui, plan_target=fplan, difficulty=4/10, breaking=no
