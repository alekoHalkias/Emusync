# Handoff: #646 Add ignore list for ROMs in console import

## Metadata
- Issue: #646
- Branch: feature/646-console-import-ignore-list
- PR: none
- Status: designed
- Created: 2026-10-31
- Fix attempts: 0

## 1. Issue
### Summary
Ignore individual ROMs in the console import results so they stop reappearing; an Ignored games button in console settings lists them and allows unignoring.
### Motivation
Unwanted files in ROM folders reappear on every scan; the existing folder ignore is session-only.
### Proposed Behavior / Steps to Reproduce
See https://github.com/alekoHalkias/Emusync/issues/646
### Affected Area
console-import/ (ResultsStep, useConsoleImport, helpers), ConsoleFoldersModal.tsx, persistence for the ignore list
### Acceptance Criteria
See issue #646.

## 2. Design
### Scope: ui only
### Backend Changes: none (per-device config key import_ignored_roms[console] = [paths], decided by user: per device, by path)
### UI Changes: per-row Ignore + Ignore selected in results; scan filters ignored paths; Ignored games button/list in ConsoleFoldersModal with Unignore; reset in ServerStatusButton clears the key
### Plan Target: fplan
### Sub-issues: none
### Difficulty: 3/10
### Backwards Compatibility: non-breaking, new optional config key. PR #645 touches the same console-import files; rebase after it merges.

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
- 2026-10-31 design: scope=ui, plan_target=fplan, difficulty=3/10, breaking=no
