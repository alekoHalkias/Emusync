# Handoff: #650 Detect new games in local and network folders from the refresh button

## Metadata
- Issue: #650
- Branch: feature/650-refresh-detect-new-games
- PR: #651
- Status: shipped
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
### Design Alignment: bulkMsg status line plus inline button; review in the existing wizard
### Visual Pattern: Refresh result message with a Review and import button
### Recommendations: scan logic in its own module because GameGrid.tsx is 702 lines

## 4. Backend Plan
### Design Alignment: TBD
### Backend Pattern: TBD
### Recommendations: TBD

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: none automated (renderer-only, no JS runner); manual checklist in the plan
### Test Cases: new ROM local; new ROM network; same ROM in both counted once; imported and ignored not counted; nothing new
### Edge Cases: no folders; no emulator; scan failure; emulator label mismatch
### Integration Points: scanNewRoms kept free of React state; wizard props override saved config only when passed

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps: see tools/plans/650-refresh-detect-new-games.md
- fplan 1: files types.ts, useConsoleImport.ts, ConsoleImport.tsx; reuses initialConsole/initialRomDirs seeding; two optional props because roots come only from saved config
- fplan 2: files console-import/scanNewRoms.ts (new); reuses annotateRoms, classifyByRoot, dedupeAndLink, ignoredRoms, device console and overview APIs, emulator detect/scan; one function since the wizard logic is inline in hook state
- fplan 3: files GameGrid.tsx; reuses handleRefreshLocations, bulkMsg, ConsoleImport; one state value and a button
- fplan 4-5: manual verification, docs

## 9. Review
### Findings: TBD
### Blocked: TBD
### Blockers: TBD

## 10. Ship
### Status: shipped
### PR: #651
### Server Sync: pending
### Doc Sync: pending

## 11. Fix Attempts
### Attempt 1: none
### Attempt 2: none
### Attempt 3: none

## 12. Log
- 2026-10-31 issue: workflow initialized
- 2026-10-31 design: scope=ui, plan_target=fplan, difficulty=4/10, breaking=no
- 2026-10-31 fplan: 5 steps written, visual_pattern=status line + Review and import button
- tplan: no automated test file (renderer only); manual cases defined in plan step 4 and Testing section
- 2026-10-31 tplan: test_file=none (manual), 5 test cases defined
- 2026-10-31 implement: started
- 2026-10-31 implement: step 1 done (initialNetworkRoot/initialLocalRoot wizard props)
- 2026-10-31 implement: step 2 done (scanNewRoms module)
- 2026-10-31 implement: step 3 done (Refresh scans for new ROMs, message + Review and import button)
- 2026-10-31 implement: step 5 done (CLAUDE.md rule and ARCHITECTURE.md section)
- 2026-10-31 implement: step 4 done (GUI behavior confirmed by user)
- 2026-10-31 ship: tests pass (566 passed, 3 skipped)
