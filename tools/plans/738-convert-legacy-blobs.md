# Plan: #738 Convert legacy save blobs once and use a single pack/unpack path

Issue: #738
Branch: feature/738-convert-legacy-blobs
PR: none
Status: implementing
Fix attempts: 0

## Goal
Every stored blob carries the #478 envelope (converted once on the server, wrapped on upload), so client pull paths drop their sniff fallbacks and raise on un-enveloped input.

## Design Alignment
- **Backend Pattern**: one-time data fix as a `_migrate` `from_version < 36` block that receives `blob_dir` (same as v35's `_backfill_console_cards`); writes via `.part` + `os.replace` (#734); hashes stay envelope-free (`_payload_sha256`, #734).
- **Recommendations**: scope cuts recorded in handoff section 2 (no `/health` gate, no single packer).

## Steps
- [x] 1. Shared converter `_envelope_legacy(data, states) -> bytes` in `src/server/sync_client.py`, beside `_pack_envelope`/`_unpack_envelope`. Enveloped input returned unchanged. `states=True`: valid gzip tar -> `_FMT_TARGZ`, else `_FMT_RAW` (mirrors `_extract_state_folder`'s legacy branch). `states=False`: opens as tar via `r:*` -> `_FMT_TARGZ` when it starts with gzip magic `\x1f\x8b`, else `_FMT_TAR`; not a tar -> `_FMT_RAW` (mirrors `_write_memcard`'s legacy branch). Plus `_envelope_file_in_place(path, states) -> bool` in `src/server/store/blobs.py`: reads the file, returns False if already enveloped, else writes `<path>.part` and `os.replace`s; returns True.
  - Files: src/server/sync_client.py, src/server/store/blobs.py
  - Reuses: `_pack_envelope`, `_unpack_envelope`, `_ENVELOPE_MAGIC`, `tarfile.open` probe as in the existing fallbacks.
  - New: both functions - the sniff logic exists only inline in four client fallbacks that this issue deletes; it must live once, server-side.
- [x] 2. Schema v36 migration: bump `_SCHEMA_VERSION` to 36; `if from_version < 36 and blob_dir is not None: _envelope_legacy_blobs(blob_dir)` which, for each of `saves`, `console_save_history`, `console_saves`, `switch_mods` (`states=False`) and `states` (`states=True`), calls `_envelope_file_in_place` on every regular file under `blob_dir/<table>/` (skip names ending `.part`; missing dir = skip). A file that fails to read is logged to stderr and skipped, never fails startup. DB rows untouched.
  - Files: src/server/store/schema.py
  - Reuses: `_migrate(conn, from_version, blob_dir)` hook and v35's skip-on-missing pattern; `_envelope_file_in_place`.
  - New: `_envelope_legacy_blobs` - small loop, mirrors `_backfill_console_cards`.
- [x] 3. Wrap un-enveloped uploads (pre-#478 clients): in `api/blobs.py:_push._store_it` call `_envelope_file_in_place(tmp, states=kind is _STATE)` before `push_*_file`, and in `api/mods.py:push_switch_mod._store_it` with `states=False`, adding 5 to `size` when it returns True. The hash is unchanged (already payload-only in `_stage_upload`; mods hash is not stored).
  - Files: src/server/api/blobs.py, src/server/api/mods.py
  - Reuses: `_envelope_file_in_place`; existing `asyncio.to_thread(_store_it)` offload.
  - New: none.
- [ ] 4. Client fallbacks removed: `_require_envelope(data) -> (fmt, payload)` in `sync_client.py` raises `ValueError("server blob has no format header; update the EmuSync server (#738)")` when `_unpack_envelope` returns None fmt. Use it in `_write_memcard`, `_extract_state_folder`, `_merge_extract_state_folder` and `pull_state`'s inline file branch; delete each legacy sniff branch. Keep `_unpack_envelope` (server and the converter use it). Temp-dir swap, `.part` writes, `_safe_extract_tar`, and `.bak` behavior per mode unchanged.
  - Files: src/server/sync_client.py
  - Reuses: `_unpack_envelope`.
  - New: `_require_envelope` - one shared raise instead of four.
- [ ] 5. Tests (real files, real SQLite; see Testing). New file src/tests/test_legacy_blob_conversion.py for converter + v36 + upload wrap (cross-cutting; no existing module owns all three). Update the existing legacy-fallback tests to the new contract.
- [ ] 6. Docs: CLAUDE.md Saves/sync envelope rule ("keep un-enveloped fallbacks for old blobs" -> server converts once in v36 and wraps old uploads; client raises on missing envelope; update server before clients). GOTCHAS.md #478 entry: replace "fallbacks are load-bearing, keep them" with the v36 conversion and rollout order. ARCHITECTURE.md: envelope section mention of v36 conversion.

## Testing
- **Test File**: src/tests/test_legacy_blob_conversion.py (new); updates in test_state_sync.py, test_memcard_folder_sync.py, test_restore_safety.py, test_console_memcard.py
- **Test Cases**:
  - converter, parametrized over legacy shapes: raw save, plain tar save, tar.gz save (states=False) -> RAW/TAR/TARGZ; tar.gz state, raw state (states=True) -> TARGZ/RAW; payload bytes unchanged; `_payload_sha256` before == after
  - converter on already-enveloped input returns it unchanged
  - v36 migration: blob dirs seeded with each legacy shape in each table (`saves`, `states`, `console_save_history`, `console_saves`, `switch_mods`) plus one enveloped file; after `schema._migrate(conn, from_version=35, blob_dir=...)` every file starts with `_ENVELOPE_MAGIC`, the enveloped one is byte-identical, `user_version == 36`, no `.part` left
  - v36 idempotent: running twice leaves bytes identical to after the first run
  - end to end: legacy save + legacy state blob placed under a Store at v35, Store opens, `GET /games/{slug}/save` returns enveloped bytes and the same `X-Save-Hash`; client `_write_memcard` / `_extract_state_folder` write the original content
  - upload wrap: `POST /games/{slug}/save` with raw un-enveloped bytes stores an enveloped file (`_FMT_RAW` for raw bytes) and returns the same hash as an enveloped push of the same content (extends `test_saves.py::test_push_save_hash_excludes_transfer_envelope` pattern); same for `POST /switch/{tid}/mods/{name}`
  - client raise: `_write_memcard`, `_extract_state_folder`, `_merge_extract_state_folder` with un-enveloped bytes raise `ValueError` and leave the target folder/file untouched
- **Edge Cases**:
  - missing blob table dir: migration skips it
  - unreadable/vanished file mid-walk: skipped, startup not failed
  - stray `<id>.part` from a crashed run: not converted, not treated as a blob
  - a raw save that happens to parse as a tar: classified TAR, same as today's client fallback (documented behavior, asserted)
- **Affected Existing Tests**:
  - test_state_sync.py::test_extract_state_folder_legacy_raw_blob -> asserts raise
  - test_memcard_folder_sync.py::test_write_memcard_legacy_raw_file_fallback -> asserts raise
  - test_restore_safety.py::test_state_extract_legacy_raw_blob -> asserts raise
  - test_console_memcard.py::test_store_serves_backfilled_card_with_same_bytes_and_hash -> pulled bytes are the RAW envelope of the original, hash unchanged
  - any other test feeding raw bytes to client unpackers: wrap with `_pack_envelope` (found by the full run)
- **Integration Points**:
  - Server PC after ship: re-run the legacy count script; expect legacy=0 in every table.

## Checklist
Schema bump: yes (v36, data-only, no DDL). New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: yes (stored blob files rewritten once, hashes unchanged).

## Not in this plan
- `/health` `blob_format` gate (the client raise is the gate).
- Single packer (`memcard_bytes` deterministic tar vs `push_state` real-mtime tar.gz; merging risks hash churn).
- Merging the three extract functions into one `_write_blob(mode)`: their modes stay distinct; only fallbacks go.

## Log
- 2026-11-16 bplan: plan written
- 2026-11-16 tplan: test plan added (7 case groups)
Step 2: step 1 converter reworked to stream (_legacy_format sniffs from the file, copyfileobj behind the header) since server blobs reach 1.5 GB; two v35 tests updated here (expected envelope) to keep the commit green
Step 3: existing API tests pushing raw bytes now expect the RAW envelope back (new conftest.raw_env helper); stored size includes the 5-byte header, matching enveloped pushes
