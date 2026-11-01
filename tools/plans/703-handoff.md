# Handoff: #703 Remove dead and broken chunked-upload code

## Metadata
- Issue: #703
- Branch: feature/703-remove-chunked-upload
- PR: none
- Status: implementing
- Created: 2026-11-01
- Fix attempts: 0

## 1. Issue
### Summary
Chunked-upload (#576) routes always fail; client and store helpers are unused. Remove them.
### Affected Area
src/server/api/blobs.py, src/server/sync_client.py, src/server/store/{blobs,_base,models}.py
### Acceptance Criteria
- [ ] All chunk code removed, no remaining references (src, tests, docs)
- [ ] Normal push/pull unchanged; tests pass

## 2. Design
### Scope: backend, deletion only
### Backend Changes: delete chunk routes + ChunkUploadRequest, _chunked_push/_normal_push/CHUNK_SIZE, _extract_memcard_archive, _chunk_dir/_chunk_status_path, ChunkStatus
### UI Changes: none
### Plan Target: bplan
### Sub-issues: none
### Difficulty: trivial
### Backwards Compatibility: routes never worked; no client calls them. The empty `chunks` dir already created on existing installs is left alone. No schema change (chunk_progress never existed).

## 3. Frontend Plan
n/a

## 4. Backend Plan
### Backend Pattern: deletion
### Recommendations: keep diff confined to the listed blocks; parallel work edits other regions of the same files.

## 5. Merged Plan
n/a

## 6. Testing Plan
### Test Cases: no new tests (pure removal); existing suite must pass; grep confirms no references.

## 7. Test Design
n/a

## 8. Implementation Steps
See tools/plans/703-remove-chunked-upload.md

## 9. Review
### Findings: TBD

## 10. Ship
### Status: shipped (PR open)

## 12. Log
- 2026-11-01 issue: workflow initialized
- 2026-11-01 plan: written, deletion only
