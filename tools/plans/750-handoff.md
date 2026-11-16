# Handoff: #750 Remove orphaned blob files and stop device removal from leaking them

## Metadata
- Issue: #750
- Branch: feature/750-orphaned-blob-files
- PR: none
- Status: created
- Created: 2026-11-16
- Fix attempts: 0

## 1. Issue
### Summary
Server blob dirs hold files with no row: saves 45 orphans (10.79 GB), states 18 (server PC, 2026-11-16).
### Motivation
Wasted disk; `remove_device` also deletes other devices' needed save generations (possible current-save loss).
### Proposed Behavior / Steps to Reproduce
Push from A and B, remove A, compare `blobs/saves/` with `SELECT id FROM saves`.
### Affected Area
`src/server/store/devices.py` (remove_device, clear_devices, merge_devices), `src/server/store/blobs.py`, one-time cleanup.
### Acceptance Criteria
- [ ] Root cause fixed, no new orphans
- [ ] Device removal keeps generations other devices need (or documented), unlinks files after commit
- [ ] Existing orphans removed once, safely (not `.uploads`, not in-flight `.part`)
- [ ] Real-SQLite regression tests

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
- 2026-11-16 issue: workflow initialized
