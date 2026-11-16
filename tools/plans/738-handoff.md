# Handoff: #738 Convert legacy save blobs once and use a single pack/unpack path

## Metadata
- Issue: #738
- Branch: feature/738-convert-legacy-blobs
- PR: none
- Status: designed
- Created: 2026-11-16
- Fix attempts: 0

## 1. Issue
### Summary
Convert every pre-#478 un-enveloped stored blob to the enveloped format once on the server, then drop the client's sniff-by-parsing fallbacks.
### Motivation
Four client pull paths keep legacy sniff fallbacks (`_write_memcard`, `_extract_state_folder`, `_merge_extract_state_folder`, `pull_state` inline), each with its own safety handling.
### Proposed Behavior / Steps to Reproduce
Server migration wraps legacy blobs (hashes unchanged, idempotent, crash-safe); client unpack paths raise on un-enveloped input.
### Affected Area
`src/server/sync_client.py`, `src/server/store/schema.py`, `src/server/api/blobs.py`, tests, docs.
### Acceptance Criteria
- [ ] Every stored legacy blob shape is converted once; hashes unchanged; conversion is idempotent and crash-safe
- [ ] No sniff fallbacks remain on the client outside the server converter
- [ ] Existing safety guarantees preserved (temp-dir swap, `.part` + `os.replace`, safe tar extraction, `.bak` behavior per mode)
- [ ] Client against an unconverted server fails clearly instead of mis-writing a save
- [ ] Real-SQLite tests for each legacy shape and each unpack mode
- [ ] CLAUDE.md drops the fallback/sniffer rules

## 2. Design
### Scope: backend only
### Backend Changes:
- Shared `_envelope_legacy(data: bytes, states: bool) -> bytes` (next to `_pack_envelope` in `sync_client.py`, already imported by server): enveloped input returned as is; states: gz tar -> TARGZ else RAW; others: tar (`r:*`) -> TARGZ if gzip magic else TAR, else RAW.
- Schema v36: `_migrate` walks `blob_dir/{saves,states,console_save_history,console_saves,switch_mods}/*` files, rewrites un-enveloped ones via `.part` + `os.replace`. Idempotent (enveloped files skipped). DB rows untouched; hashes are payload hashes.
- `api/blobs.py:_stage_upload` (or its caller, which knows the kind): wrap an un-enveloped staged upload with the same function.
- Client: `_require_envelope(data) -> (fmt, payload)` raises `ValueError` ("server blob has no format header; update the EmuSync server") on missing envelope; used by the four pull paths; their sniff branches deleted.
### UI Changes: none
### Plan Target: bplan
### Sub-issues: none
### Scope cuts: no `/health` gate (the raise is the gate); no single packer (deterministic memcard tar vs real-mtime state tar.gz differ on purpose; merging risks hash churn).
### Difficulty: 5/10
### Backwards Compatibility: non-breaking; server must be updated before clients.

## 3. Frontend Plan
### Design Alignment: n/a
### Visual Pattern: n/a
### Recommendations: n/a

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
- 2026-11-16 issue: workflow initialized (existing issue #738)
- 2026-11-16 design: scope=backend, plan_target=bplan, difficulty=5/10, breaking=no
