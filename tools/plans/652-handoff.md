# Handoff: #652 Reduce vertical space in console import results step

## Metadata
- Issue: #652
- Branch: feature/652-compact-import-results
- PR: none
- Status: planned
- Created: 2026-10-31
- Fix attempts: 0

## 1. Issue
### Summary
Compact the results step of the console import wizard so more ROM rows fit on screen.
### Motivation
Many stacked rows above and below the ROM list leave few visible rows.
### Proposed Behavior / Steps to Reproduce
- Local + Network folder on one line
- Search, filter, title cleanup, Ignore selected, Select all on one wrapping line
- Folders-scanned toggle and linked-games note inline with folder row
- Ignored-files note folded into selection-count area
- Tighter ROM row padding
- Push saves/states checkboxes in the Back/Import action row
### Affected Area
console-import/ResultsStep.tsx, console-import/LocationsBlock.tsx
### Acceptance Criteria
See issue #652.

## 2. Design
### Scope: ui
### Backend Changes: none
### UI Changes: layout-only edits in ResultsStep.tsx and LocationsBlock.tsx
### Plan Target: fplan
### Sub-issues: none
### Difficulty: 2/10
### Backwards Compatibility: no breaking changes

## 3. Frontend Plan
### Design Alignment: layout-only, existing btn/flex inline styles
### Visual Pattern: wrapping flex rows, no new classes
### Recommendations: none

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
### Steps: see tools/plans/652-compact-import-results.md
- 1 LocationsBlock.tsx; reuses Row, btn, showFolders; no new code
- 2 ResultsStep.tsx; reuses existing handlers; JSX containers merge
- 3 ResultsStep.tsx; reuses inline styles
- 4 ResultsStep.tsx; reuses ci-check, modal-actions
- 5-7 typecheck, no tests (no renderer test infra), no docs

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
- 2026-10-31 design: scope=ui, plan_target=fplan, difficulty=2/10, breaking=no
- 2026-10-31 fplan: 7 steps written, visual_pattern=wrapping flex rows
