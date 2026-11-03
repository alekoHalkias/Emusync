# Plan: #737 Unify save, state and memcard storage into one slot model and payload format

Issue: #737
Branch: feature/737-save-slot-model
PR: none
Status: planned
Fix attempts: 0

## Goal
Make per-game saves/states and shared console memcards run through one store core, one baseline/conflict helper and one pack/unpack pair, so a sync fix lands once, with the smallest migration that gets there.

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

### Phase A - one store core for memcards (candidate sub-issue 1, no wire change)
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

### Phase B - one pack/unpack pair, legacy blobs converted once (candidate sub-issue 2, no wire change)
- [ ] B1. Schema v36 (or a startup pass gated by a `server_settings` flag): walk every stored blob in `saves`, `states`, `console_save_history`, `switch_mods`; for un-enveloped ones sniff once (tar.gz -> TARGZ, tar -> TAR, else RAW) and rewrite with the envelope via `.part` + `os.replace`. Stored hash is unchanged because it is already envelope-free (`_payload_sha256`). Back up nothing: content bytes are identical, only a 5-byte header is prepended.
  - Files: src/server/store/schema.py or src/server/store/blobs.py
  - Reuses: `_pack_envelope`, `_payload_sha256`, the existing sniff logic moved here
  - New: one-shot converter - the only place the sniff logic should survive
- [ ] B2. Single client unpacker: `_write_blob(dest, data, mode)` with `mode` in `replace` (saves/memcards/mods), `state` (backup-all then file-wise move) and `merge` (backup only overwritten files). Replaces `_write_memcard`, `_extract_state_folder`, `_merge_extract_state_folder` and the inline branch in `pull_state`. Keeps `_extract_tar_to_tmp`, `_safe_extract_tar`, `.part` + `os.replace`, `CardFormatMismatch`. Un-enveloped input raises instead of sniffing.
  - Files: src/server/sync_client.py, src/cli/transfer.py (ROM folder receive path calls `_write_memcard`)
  - Reuses: `_extract_tar_to_tmp`, `_safe_extract_tar`, `_write_memcard_raw_bytes`, `_backup_state_files`
  - New: dispatcher only - three near-identical extract paths collapse into it
- [ ] B3. Single client packer: `_pack_path(path, gzip, name_prefix)` used by `memcard_bytes`, `push_state` and transfer.py; hash helper stays `_memcard_payload_bytes` (renamed `_payload_bytes`) so local hashes do not change.
  - Files: src/server/sync_client.py, src/cli/transfer.py
  - Reuses: `_memcard_payload_bytes` deterministic tar, `_pack_envelope`
  - New: none
- [ ] B4. Compatibility gate: a client must not drop sniff fallbacks while talking to an unconverted server. Add `blob_format: 1` to `/health`; `SyncClient` refuses blob pulls with a clear error if absent. Server PC updates first (it does today via the post-commit sync).
  - Files: src/server/api/_core.py or health route, src/server/sync_client.py
  - Reuses: `SyncClient.health`
  - New: one health field - old servers must be detectable

### Phase C - reconcile client (optional, candidate sub-issue 3)
- [ ] C1. Give `SyncClient` save methods a slot prefix (`games/{slug}/save` vs `consoles/{key}/memcard`), since the routes now mirror each other after A5. `_MemcardClient` shrinks to the GC Dolphin card-format pre-pull check. Low value on its own; skip if A+B land cleanly.
  - Files: src/server/sync_client.py, src/cli/run_ps2.py, src/cli/run.py, src/cli/console.py
  - Reuses: `_reconcile_save` unchanged
  - New: none

### Tests and docs
- [ ] T. Tests, real SQLite, no mocks: A3 migration from a v34 DB with a pre-#480 card (history backfilled, pull returns same bytes and hash); memcard push/pull/history/restore/baseline via routes unchanged (existing `test_console_memcard.py`, 30 tests, is the regression net); integrity sweep includes a console card; B1 converts each legacy shape and the hash is unchanged; B2 rejects un-enveloped input; B4 old-server detection. Existing suites touched: test_console_memcard, test_saves, test_state_sync, test_run_reconcile, test_store_internals, test_memcard_folder_sync, test_restore_safety, test_gc_card_format_mismatch, test_conflicts.
- [ ] D. Docs: CLAUDE.md "Saves / sync" - drop "keep un-enveloped fallbacks" and "don't add byte sniffers" (after B), replace memcard table list with "console cards use the shared blob core keyed by console_key"; GOTCHAS.md entry for v35/v36; ARCHITECTURE.md blob section; backend design guide gains "blob tables share one core keyed by owner column".

## Sizing
| Phase | Files | Risk | Migration |
|---|---|---|---|
| A | store/blobs.py, store/conflicts.py, store/schema.py, api/blobs.py, (store/devices.py) | low-medium: server only, routes unchanged | v35, additive backfill |
| B | sync_client.py, cli/transfer.py, schema or blobs.py, health route | medium: touches every pull path on clients | v36, rewrites blob headers in place |
| C | sync_client.py, cli/run_ps2.py, run.py, console.py | low | none |

## Checklist
Schema bump: yes (v35 Phase A, v36 Phase B). New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no (blob files rewritten in place in B1).

## Not in this plan
- A single `slots` table replacing saves/states/console tables (see Recommendations).
- A manifest payload format with per-file hashes (file separately when per-file diff/delta sync is wanted).
- A state sync baseline (states currently conflict-check by hash only); trivial after A4, separate issue.
- Any GUI change.

## Log
- 2026-11-02 bplan: outline written; awaiting user decision on split (A / B / C as sub-issues) before tplan
