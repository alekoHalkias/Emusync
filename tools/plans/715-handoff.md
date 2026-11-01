# Handoff: #715 Prevent data loss on failed or empty transfers

## Metadata
- Issue: #715
- Branch: feature/715-prevent-transfer-data-loss
- PR: none
- Status: designed
- Created: 2026-11-01
- Fix attempts: 0

## 1. Issue
### Summary
Failed or empty transfers can destroy or hide ROMs, saves and states (audit findings).
### Motivation
Data-loss paths in download_transfer, _pull baseline recording, and _stage_upload.
### Proposed Behavior / Steps to Reproduce
See https://github.com/alekoHalkias/Emusync/issues/715
### Affected Area
src/server/sync_client.py, src/server/api/blobs.py, src/server/store/blobs.py, src/server/api/_core.py, src/gui/electron/files.ts
### Acceptance Criteria
- .part download + verify + os.replace
- baseline recorded only after confirmed transfer
- zero-byte uploads rejected (400)
- _is_stale handles naive timestamps; upload writes off event loop; chunked file hash; extensionless ROMs accepted
- regression tests

## 2. Design
### Scope: backend (plus one-line Python snippet change in files.ts)
### Backend Changes: download_transfer to .part + os.replace and allow extensionless names; _pull records baseline via a Starlette BackgroundTask on the FileResponse (runs only after the body is fully sent, no new endpoint or client change); _stage_upload rejects size 0 with 400 and offloads writes via run_in_executor; _is_stale treats naive stamps as UTC; files:get-file-hash chunked read.
### UI Changes: none (files.ts hash snippet only, no IPC signature change)
### Plan Target: bplan
### Sub-issues: none (MAC device-merge risk is a separate follow-up issue)
### Difficulty: 3/10
### Backwards Compatibility: no breaking changes; endpoints, IPC and schema unchanged.

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
- 2026-11-01 design: scope=backend, plan_target=bplan, difficulty=3/10, breaking=no
