# Handoff: #737 Run console memory cards through the shared save store and sync paths

## Metadata
- Issue: #737
- Branch: feature/737-save-slot-model
- PR: none
- Status: implementing
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
### Sub-issues: rescoped 2026-11-02. #737 = Phases A + C (store core + client). #738 = legacy blob conversion + single pack/unpack. #739 = evaluate manifest format + merged tables (deferred).
### Difficulty: 6/10 after rescope (was 10/10 for the full rewrite)
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
### Test File: src/tests/test_console_memcard.py (extend), test_integrity.py, test_conflicts.py; no new file
### Test Cases: A3 backfill migration (+idempotent, +skips cards with history), shared baseline/conflict helper dedupe, route headers/shapes unchanged, pull baseline after body delivered, console card integrity classification, SyncClient slot prefix via live_server, GC mismatch tests unchanged
### Edge Cases: no history and no live file, missing blob file during migration, same id string across owner types, restore keeps card_format, game delete still cascades save_conflicts
### Integration Points: Store init runs _migrate with blob_dir; _DEVICE_REFS; two existing tests rewritten (live-slot assertions); manual dev-server run for GUI paths
### Outline:
Backend: A1 parameterize blob core by owner column; A2 memcard store methods on the core; A3 v35 backfill of pre-#480 cards; A4 shared baseline/conflict helpers; A5 memcard routes via _BlobKind handlers; A6 device-merge refs; C1 slot prefix on SyncClient, shrink _MemcardClient.
Tests: extend test_console_memcard/test_integrity/test_conflicts; rewrite two live-slot tests.
Docs: CLAUDE.md memcard rule, GOTCHAS v35, ARCHITECTURE blob section, backend design guide.
### Summary: Console memory cards run on the same store core, handlers and client paths as per-game saves, with an additive v35 backfill and no external API change.

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps: see tools/plans/737-save-slot-model.md
- A1-A6 (Phase A, store core for memcards, v35): store/blobs.py, store/conflicts.py, store/schema.py, api/blobs.py, store/devices.py. Reuses table-parameterized blob core and _BlobKind handlers; only new code is the v35 backfill (only lossless way to retire console_saves).
- C1: slot prefix on SyncClient, shrink _MemcardClient. No new code.
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
- 2026-11-02 rescope: #737 = A + C (difficulty 6, non-breaking); B -> #738; D/E -> #739
- 2026-11-04 tplan: test_file=src/tests/test_console_memcard.py (+integrity, conflicts), 7 test cases defined
- 2026-11-04 implement: started, Status=implementing
- 2026-11-04 implement: step A1 done (blob core helpers take owner_col, default game_slug; console_key rows carry card_format)
- 2026-11-04 implement: step A2 done (memcard store methods on shared core via console_save_history; dead folder-archive helpers removed; console_saves no longer written)
- 2026-11-04 implement: step A3 done (schema v35 backfills console_saves-only cards into console_save_history; 4 migration tests)
