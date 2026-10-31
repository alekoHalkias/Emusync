# Handoff: #664 Refresh locations reports games but they are not shown in the library

## Metadata
- Issue: #664
- Branch: feature/664-refresh-locations-games-not-shown
- PR: #665
- Status: shipped
- Created: 2026-10-31
- Fix attempts: 0

## 1. Issue
### Summary
Refresh locations reports 5 games found/linked but they do not appear in the grid.
### Motivation
Count and visible result disagree.
### Proposed Behavior / Steps to Reproduce
Open console grid, press Refresh locations, compare reported count with grid.
### Affected Area
GameGrid.tsx handleRefreshLocations; console-import/scanNewRoms.ts; helpers.ts dedupeAndLink.
### Acceptance Criteria
- Reported count matches visible/importable games.
- Linked games become visible or message explains how.

## 2. Design
### Scope: ui (renderer only)
### Backend Changes: none
### UI Changes: GameGrid handleRefreshLocations, scanNewRoms count vs linked ROMs
### Plan Target: fplan
### Sub-issues: none
### Difficulty: 3/10
### Backwards Compatibility: no breaking changes

## 3. Frontend Plan
### Design Alignment: no visual change
### Recommendations: none

## 4. Backend Plan
TBD

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: none (no renderer harness)
### Test Cases: manual close-with-X check
### Edge Cases: no successful links -> no refresh
### Integration Points: GameGrid onChanged
### Outline
Frontend: useConsoleImport.linkShareGames calls onImported() after successful links.
Tests: no renderer harness; make lint + make test-changed + manual check.
Docs: none.
### Summary
Auto-linked share games now refresh the grid immediately instead of only on the wizard's Done button.

## 7. Test Design
TBD

## 8. Implementation Steps
1. useConsoleImport.ts linkShareGames: call onImported() after links. Reuses onImported prop; no new code.
2. Tests: no renderer harness; typecheck + manual.
3. Docs: none.

## 9. Review
### Findings: none
### Blocked: no
### Blockers: none

## 10. Ship
### Status: shipped
### PR: #665
### Server Sync: done
### Doc Sync: done (none needed)

## 11. Fix Attempts
none

## 12. Log
- 2026-10-31 issue: workflow initialized
- 2026-10-31 design: scope=ui, plan_target=fplan, difficulty=3/10, breaking=no
- 2026-10-31 fplan: 3 steps written, visual_pattern=none
- 2026-10-31 tplan: test_file=none, 1 manual case defined
- 2026-10-31 implement: step 1 done (onImported after share links); lint/tests pass, pre-existing tsc errors elsewhere
- 2026-10-31 review: 0 findings, blocked=no
- 2026-10-31 ship: server sync done; doc sync none needed
