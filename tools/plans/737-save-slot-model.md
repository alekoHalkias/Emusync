# Plan: #737 Run console memory cards through the shared save store and sync paths

Issue: #737
Branch: feature/737-save-slot-model
PR: none
Status: planned
Fix attempts: 0

## Goal
Make shared console memcards run through the same store core, baseline/conflict helpers, API handlers and client paths as per-game saves, so a sync fix lands once. Phase B moved to #738; D/E deferred to #739.

## What the code actually looks like (findings that reshape the issue)
1. Per-game saves and states are already unified: `store/blobs.py` has a table-parameterized core (`_push_blob_file`, `_pull_blob_path`, `_list_blob_history`, `_restore_blob`, `_classify_blob`) and `api/blobs.py` has `_BlobKind`-parameterized handlers. The duplication is memcards only.
2. Memcards keep two stores for one thing: a live single-row table `console_saves` plus `console_save_history`. `pull_console_save_path` already prefers the history row, so `console_saves` is effectively a cached "newest history row".
3. `_is_folder_upload` / `_archive_memcard_folder` in `store/blobs.py` look dead: staged uploads are always `<uuid>.part`, so the suffix check never matches. Verify with a test before deleting.
4. The payload format is already self-describing: the #478 envelope (`ES1\0` + fmt byte: RAW / TAR / TARGZ). The real pain is the un-enveloped legacy blobs still on disk, which force sniff fallbacks in `_write_memcard`, `_extract_state_folder`, `_merge_extract_state_folder` and `pull_state`.
5. `_MemcardClient` (`cli/run_ps2.py`, ~45 lines) is a thin adapter that also carries the GC Dolphin card-format check (#428). Deleting it moves that check, it does not remove it.
6. Separate baseline/conflict tables are partly forced: `save_conflicts.game_slug` is an FK to `games` with cascade delete; console rows have no game to reference.

## Design Alignment
- **Backend Pattern**: Extend the existing table-parameterized store core (the pattern saves/states already use) to take an owner column, rather than introducing new slot tables. Same for baseline and conflict helpers. Routes stay; memcard routes become `_BlobKind`-style wrappers like save/state.
- **Recommendations**:
  - Unify code, not tables. A single `slots` table would need a lossy-risk migration of every save row, lose the `games` FK cascade, and violate the guide's "never rename or drop" rule, for no behavior gain over a parameterized core.
  - Do not introduce a new manifest payload format now. Instead convert legacy un-enveloped blobs once (server migration) and delete the client sniff fallbacks. A manifest (per-file hashes) is worth it only when a feature needs per-file diff or delta sync; file that separately.
  - Keep `_MemcardClient` but shrink it to the GC format hook, or fold it into a slot prefix on `SyncClient` (Phase C, optional).

## Steps

### Phase A - one store core for memcards (no wire change)
- [ ] A1. Parameterize the blob core by owner column: `_newest_row`, `_push_blob_file`, `_prune_history`, `_list_blob_history`, `_restore_blob`, `_classify_blob`, `_last_good_version` take `(table, owner_col, owner_id)`; save/state wrappers pass `("game_slug", slug)`. Observable: no behavior change, existing save/state tests pass.
  - Files: src/server/store/blobs.py
  - Reuses: the existing table-parameterized helpers (only the hardcoded `game_slug` column becomes a parameter)
  - New: none
- [ ] A2. Rewrite memcard store methods on the core against `console_save_history` (owner_col `console_key`, extra `card_format` column carried through as an optional field). Current card = newest history row. `push_console_save_file`, `pull_console_save_path`, `get_console_save_meta`, `list_console_save_history`, `restore_console_save` keep their names and return shapes. Delete `_push_console_history_row`, `_prune_console_history`, and (if A0 test confirms dead) `_is_folder_upload`/`_archive_memcard_folder`. Stop writing `console_saves`.
  - Files: src/server/store/blobs.py
  - Reuses: A1 core; `restore_console_save` becomes `_restore_blob`
  - New: none
- [ ] A3. Schema v35 migration: for each `console_saves` row whose hash has no matching `console_save_history` row (pre-#480 cards), insert a history row and copy `blobs/console_saves/<key>` to `blobs/console_save_history/<id>`. `console_saves` table is left in place, unused (guide: never drop). Bump `_SCHEMA_VERSION` to 35 (checked free on all remote branches 2026-11-02).
  - Files: src/server/store/schema.py
  - Reuses: `_try`, existing `from_version < N` pattern
  - New: one migration block - backfill is the only lossless way to retire the live table
- [ ] A4. Parameterize baseline and conflict helpers: `_set_baseline/_get_baseline(table, owner_col, ...)` and `_add_conflict(table, owner_col, ...)`; existing public methods (`set_save_sync_baseline`, `set_console_save_sync_baseline`, `add_conflict`, `add_console_conflict`) become one-line wrappers. Tables unchanged.
  - Files: src/server/store/blobs.py, src/server/store/conflicts.py
  - Reuses: existing SQL, deduplicated
  - New: none
- [ ] A5. Fold memcard routes into the `_BlobKind` handlers: add `owner` lookup + optional `X-Card-Format` header to `_BlobKind` so `/consoles/{key}/memcard*` (pull, push, meta, sync-baseline, history, restore) call `_pull/_push/_meta/_history/_restore`. Paths, headers and response shapes unchanged. Integrity sweep covers console cards for free (`_classify_blob`).
  - Files: src/server/api/blobs.py
  - Reuses: `_pull`, `_push`, `_meta`, `_history`, `_restore`, `_stage_upload`
  - New: none
- [ ] A6. Device-merge refs: drop `console_saves` from `_DEVICE_REFS` only if A3 leaves it empty-and-unused; otherwise keep (harmless).
  - Files: src/server/store/devices.py
  - Reuses: `_DEVICE_REFS`
  - New: none

### Phase C - reconcile client
- [ ] C1. Give `SyncClient` save methods a slot prefix (`games/{slug}/save` vs `consoles/{key}/memcard`), since the routes now mirror each other after A5. `_MemcardClient` shrinks to the GC Dolphin card-format pre-pull check.
  - Files: src/server/sync_client.py, src/cli/run_ps2.py, src/cli/run.py, src/cli/console.py
  - Reuses: `_reconcile_save` unchanged
  - New: none

### Tests and docs
- [ ] T. Tests, real SQLite, no mocks: A3 migration from a v34 DB with a pre-#480 card (history backfilled, pull returns same bytes and hash); memcard push/pull/history/restore/baseline via routes unchanged (existing `test_console_memcard.py`, 30 tests, is the regression net); integrity sweep includes a console card; C1 GC card-format check still blocks a mismatched pull. Existing suites touched: test_console_memcard, test_saves, test_state_sync, test_run_reconcile, test_store_internals, test_gc_card_format_mismatch, test_conflicts.
- [ ] D. Docs: CLAUDE.md "Saves / sync" - replace memcard table list with "console cards use the shared blob core keyed by console_key"; GOTCHAS.md entry for v35; ARCHITECTURE.md blob section; backend design guide gains "blob tables share one core keyed by owner column".

## Sizing
| Phase | Files | Risk | Migration |
|---|---|---|---|
| A | store/blobs.py, store/conflicts.py, store/schema.py, api/blobs.py, (store/devices.py) | low-medium: server only, routes unchanged | v35, additive backfill |
| C | sync_client.py, cli/run_ps2.py, run.py, console.py | low | none |

## Checklist
Schema bump: yes (v35). New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
- Legacy blob conversion and single pack/unpack path: #738.
- Manifest payload format and merged tables: #739 (evaluate later).
- A state sync baseline (states currently conflict-check by hash only); trivial after A4, separate issue.
- Any GUI change.

## Log
- 2026-11-02 bplan: outline written; awaiting user decision on split (A / B / C as sub-issues) before tplan
- 2026-11-02 rescope: #737 = Phases A + C; Phase B -> #738; Phases D/E -> #739
