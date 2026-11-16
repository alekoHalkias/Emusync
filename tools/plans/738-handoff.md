# Handoff: #738 Convert legacy save blobs once and use a single pack/unpack path

## Metadata
- Issue: #738
- Branch: feature/738-convert-legacy-blobs
- PR: none
- Status: implementing
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
### Design Alignment: one-time data fix in _migrate (v36, blob_dir like v35); .part + os.replace; envelope-free hashes.
### Backend Pattern: shared converter in sync_client.py + _envelope_file_in_place in store/blobs.py used by migration and both upload routes.
### Recommendations: scope cuts per section 2.

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: src/tests/test_legacy_blob_conversion.py (new) + updates to 4 existing test files
### Test Cases: converter shapes (5) + already-enveloped; v36 migration all tables; idempotency; end-to-end pull bytes/hash; upload wrap (save, mod); client raise (3 paths)
### Edge Cases: missing dir, vanished file, stray .part, raw-that-parses-as-tar
### Integration Points: server PC legacy count = 0 after ship
### Outline:
Backend
- 1. _envelope_legacy (sync_client.py) + _envelope_file_in_place (store/blobs.py)
- 2. schema v36: wrap every legacy file in the five blob dirs, idempotent, .part + os.replace
- 3. upload routes (_push, push_switch_mod) wrap pre-#478 uploads
- 4. client: _require_envelope raises; four sniff fallbacks deleted
Tests
- 5. test_legacy_blob_conversion.py + legacy-fallback tests flipped to "raises"
Docs
- 6. CLAUDE.md, GOTCHAS.md, ARCHITECTURE.md envelope rules
### Summary: The server converts all pre-#478 blobs to the enveloped format once (v36) and wraps old uploads, so clients drop every sniff fallback and fail clearly on un-enveloped data; hashes do not change.

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps: see tools/plans/738-convert-legacy-blobs.md
- [done] Step 1: sync_client.py, store/blobs.py - reuses _pack/_unpack_envelope; new _envelope_legacy + _envelope_file_in_place because the sniff only exists inline in the fallbacks being deleted.
- Step 2: schema.py - reuses _migrate blob_dir hook (v35 pattern); new _envelope_legacy_blobs loop.
- Step 3: api/blobs.py, api/mods.py - reuses _envelope_file_in_place in existing _store_it offloads.
- Step 4: sync_client.py - new _require_envelope replaces four sniff branches.
- Step 5: tests - extend test_state_sync.py, test_memcard_folder_sync.py, test_restore_safety.py, test_saves.py.
- Step 6: CLAUDE.md, GOTCHAS.md, ARCHITECTURE.md.

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
- 2026-11-16 bplan: 6 steps written, backend_pattern=v36 data migration + shared converter
- 2026-11-16 tplan: test_file=src/tests/test_legacy_blob_conversion.py, 7 test case groups defined
- 2026-11-16 implement: step 1 done (_envelope_legacy + _envelope_file_in_place)
