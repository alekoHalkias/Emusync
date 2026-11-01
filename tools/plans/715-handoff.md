# Handoff: #715 Prevent data loss on failed or empty transfers

## Metadata
- Issue: #715
- Branch: feature/715-prevent-transfer-data-loss
- PR: none
- Status: implementing
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
### Design Alignment: fits thin-route/store pattern; no schema, endpoint or protocol change.
### Backend Pattern: Starlette BackgroundTask on FileResponse records the baseline after delivery; .part + os.replace for downloads.
### Recommendations: add BackgroundTask pattern to backend-design-guide.md.

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: src/tests/test_transfer_dataloss_715.py
### Test Cases: ROM hash mismatch / mid-stream failure / success / extensionless via real http.server; baseline absent before background and present after for save and memcard; empty POST returns 400 for save, state, memcard
### Edge Cases: naive and garbage timestamps in _is_stale; 204 pull records no baseline; valid upload after rejected empty one
### Integration Points: FileResponse.background via ASGI client fixture; files.ts hash checked manually against sha256sum
### Outline:
Backend: 1 .part download + extensionless; 2 baseline via BackgroundTask (save + memcard); 3 reject empty uploads; 4 offload upload writes; 5 _is_stale naive handling; 6 chunked hash in files.ts
Tests: test_transfer_dataloss_715.py (real SQLite, real http.server, no mocks)
Docs: design guide, GOTCHAS, CLAUDE.md rule line
### Summary: Failed, partial or empty transfers can no longer overwrite or hide ROMs, saves or states.

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps: see tools/plans/715-prevent-transfer-data-loss.md
- Step 1: sync_client.py; reuses download_transfer loop; no new code.
- Step 2: api/blobs.py; reuses FileResponse + set_*_sync_baseline; no new code.
- Step 3: api/blobs.py; reuses _stage_upload cleanup block; no new code.
- Step 4: api/blobs.py; reuses create_rom_transfer executor pattern; no new code.
- Step 5: api/_core.py; reuses _presence_tick naive-UTC handling; no new code.
- Step 6: gui/electron/files.ts; edits existing python snippet; no new code.
- Step 7: tests/test_transfer_dataloss_715.py; new file, regression tests required by policy.
- Step 8: docs; design guide, GOTCHAS, CLAUDE.md.

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
- 2026-11-01 bplan: 8 steps written, backend_pattern=BackgroundTask baseline + .part download
- 2026-11-01 tplan: test_file=src/tests/test_transfer_dataloss_715.py, 9 test cases defined
- Step 7 (tests): tests/test_transfer_dataloss_715.py; reuses conftest make_client/AUTH and test_saves baseline pattern; new file justified by per-issue regression convention.
- 2026-11-01 implement: step 1 done (download ROMs via .part then replace, allow extensionless)
- 2026-11-01 implement: step 1 done (download ROMs via .part then replace, allow extensionless)
- 2026-11-01 implement: step 2 done (record pull baseline after body is sent)
- 2026-11-01 implement: step 3 done (reject empty uploads with 400)
- 2026-11-01 implement: step 4 done (offload upload writes to executor (same edit as step 3))
- 2026-11-01 implement: step 5 done (_is_stale treats naive timestamps as UTC)
- 2026-11-01 implement: step 6 done (chunked hash in files:get-file-hash)
- 2026-11-01 implement: step 7 done (regression tests (fail on main, pass here))
