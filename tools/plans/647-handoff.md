# Handoff: #647 Fix missing network_share_id column on databases at schema v30

## Metadata
- Issue: #647
- Branch: feature/647-fix-network-share-id-migration
- PR: none
- Status: created
- Created: 2026-10-31
- Fix attempts: 0

## 1. Issue
### Summary
Databases already at schema v30 (from closed #642/#643) skip #644's v30 migration, so consoles.network_share_id is missing and console queries fail.
### Motivation
Console settings shows no folders; GET /devices/{id}/consoles returns 500 on the server PC.
### Proposed Behavior / Steps to Reproduce
See https://github.com/alekoHalkias/Emusync/issues/647
### Affected Area
schema.py migration, consoles.py, ConsoleFoldersModal.tsx, test_network_rom.py
### Acceptance Criteria
See issue #647.

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
