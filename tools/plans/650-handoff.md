# Handoff: #650 Detect new games in local and network folders from the refresh button

## Metadata
- Issue: #650
- Branch: feature/650-refresh-detect-new-games
- PR: none
- Status: designed
- Created: 2026-10-31
- Fix attempts: 0

## 1. Issue
### Summary
Refresh locations also scans the console's local and network folders for ROMs not yet in the library and offers to import them.
### Motivation
Today refresh only validates saved ROM paths; new ROMs require reopening the full Add console wizard.
### Proposed Behavior / Steps to Reproduce
See https://github.com/alekoHalkias/Emusync/issues/650
### Affected Area
GameGrid.tsx handleRefreshLocations, useBrokenRoms.refresh, console-import scan/dedupe/ignoredRoms
### Acceptance Criteria
See issue #650.

## 2. Design
### Scope: ui only
### Backend Changes: none
### UI Changes: Refresh resolves the console emulator, scans its folders, drops linked and ignored ROMs, reports N new games with a Review and import button opening the prefilled wizard (user decision: report count and open wizard)
### Plan Target: fplan
### Sub-issues: none
### Difficulty: 4/10
### Backwards Compatibility: non-breaking; frontend only; network scan cost on each click, show progress

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
- 2026-10-31 issue: workflow initialized
- 2026-10-31 design: scope=ui, plan_target=fplan, difficulty=4/10, breaking=no
