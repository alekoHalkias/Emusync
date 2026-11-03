# Handoff: #737 Unify save, state and memcard storage into one slot model and payload format

## Metadata
- Issue: #737
- Branch: feature/737-save-slot-model
- PR: none
- Status: planned
- Created: 2026-11-02
- Fix attempts: 0

## 1. Issue
### Summary
Rewrite the save-blob layer around a single slot concept `(owner_type: game|console, owner_id, kind: save|state)` and a single manifest-based payload format, replacing parallel per-game/console implementations and raw/tar/enveloped blob variants.
### Motivation
Highest fix churn in the codebase (#460, #478, #692, #699, #717, #718, #734). Duplicate tables (`saves`/`save_sync_baseline`/`save_conflicts` vs `console_saves`/`console_save_history`/`console_save_sync_baseline`/`console_save_conflicts`), `_MemcardClient` imitating `SyncClient`, multiple payload shapes forcing envelope-free hashing rules and permanent fallbacks, three extract paths.
### Proposed Behavior / Steps to Reproduce
1. Slot tables for blobs/history, baseline, conflicts; memcards become console-owned slots.
2. Manifest (path, size, sha256 per file) + contents payload; hash from manifest; one manifest-driven extract/merge/restore keeping existing safety guarantees.
3. One reconcile function on slots; remove `_MemcardClient`.
4. Schema bump migrates `console_save*` tables and converts legacy blobs once.
5. CLI exit codes, GUI conflict flow and REST conflict-check endpoints stay compatible or are versioned explicitly.
### Affected Area
`server/sync_client.py`, `server/store/{blobs,conflicts,schema}.py`, `server/api/{blobs,conflicts}.py`, `cli/{run_reconcile,run_ps2,run,console,game}.py`, GUI callers of save/memcard routes, tests, docs.
### Acceptance Criteria
- Game saves/states and console memcards/states share slot tables and store methods
- Single manifest payload format, hash defined once
- `_MemcardClient` and duplicated console paths removed
- Migration preserves history, baselines, conflicts; restorable
- No raw/enveloped fallback readers after migration
- Existing safety guarantees preserved
- Real-SQLite integration tests for migration, slot push/pull/conflict, restore
- Docs updated
- Split into sub-issues during design

## 2. Design
### Scope: backend only
### Backend Changes:
- Store already has a table-parameterized blob core in `store/blobs.py` (`_push_blob`, `_pull_blob_path`, `_list_blob_history`, `_restore_blob`) shared by `saves`/`states`; memcards (`console_saves`, `console_save_history`, `console_save_sync_baseline`, `console_save_conflicts`) are the outlier.
- Slot tables keyed `(owner_type, owner_id, kind)`; migrate existing rows; keep REST routes in `api/blobs.py`/`api/conflicts.py` as facades.
- Manifest payload format in `sync_client.py`; one manifest-driven extract/restore; one-time server-side legacy blob conversion; server keeps accepting/serving legacy format for not-yet-updated clients.
- Slot-aware `_reconcile_save` in `cli/run_reconcile.py`; remove `_MemcardClient` (`cli/run_ps2.py`).
### UI Changes: none. GUI push/pull shells out to CLI (#479); history/restore/conflicts use existing REST routes via `api.ts`, kept as facades. CLI exit codes unchanged.
### Plan Target: bplan
### Sub-issues:
1. Slot schema + migration + store/API facades (no wire change)
2. Manifest payload format + single extract path + legacy conversion + legacy upload acceptance
3. Unified slot reconcile; remove `_MemcardClient`
4. Docs/rules cleanup
### Difficulty: 10/10 (8 base + 2 breaking)
### Backwards Compatibility: breaking. Lossless one-way schema migration (back up DB + blob dir first). Mixed-version devices: server must accept legacy uploads and serve readable blobs until all clients migrate. No REST, IPC, config or CLI exit-code changes.

## 3. Frontend Plan
### Design Alignment: TBD
### Visual Pattern: TBD
### Recommendations: TBD

## 4. Backend Plan
### Design Alignment: saves/states already share a table-parameterized core (store/blobs.py, api/blobs.py _BlobKind); memcards are the only duplicate. Payload is already self-describing via the #478 envelope.
### Backend Pattern: extend the existing core with an owner column instead of new slot tables; parameterize baseline/conflict helpers; fold memcard routes into _BlobKind handlers.
### Recommendations: unify code not tables; replace "manifest format" with one-time envelope conversion of legacy blobs; keep _MemcardClient (GC format hook) unless Phase C is wanted.

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
### Steps: see tools/plans/737-save-slot-model.md
- A1-A6 (Phase A, store core for memcards, v35): store/blobs.py, store/conflicts.py, store/schema.py, api/blobs.py, store/devices.py. Reuses table-parameterized blob core and _BlobKind handlers; only new code is the v35 backfill (only lossless way to retire console_saves).
- B1-B4 (Phase B, legacy blob conversion + single pack/unpack, v36): sync_client.py, cli/transfer.py, schema/blobs.py, health route. Reuses _pack_envelope, _extract_tar_to_tmp, _safe_extract_tar; new: one-shot converter, _write_blob dispatcher, health field (old servers must be detectable).
- C1 (optional): slot prefix on SyncClient, shrink _MemcardClient. No new code.
- T, D: tests (real SQLite) and docs.

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
- 2026-11-02 issue: workflow initialized
- 2026-11-02 design: scope=backend, plan_target=bplan, difficulty=10/10, breaking=yes
- 2026-11-02 bplan: 3 phases (A/B/C) + tests/docs written, backend_pattern=owner-column-parameterized blob core; paused for split decision before tplan
