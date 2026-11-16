# Plan: #738 Convert legacy save blobs once and use a single pack/unpack path

Issue: #738
Branch: feature/738-convert-legacy-blobs
PR: none
Status: planned
Fix attempts: 0

## Goal
Every stored blob carries the #478 envelope (converted once on the server, wrapped on upload), so client pull paths drop their sniff fallbacks and raise on un-enveloped input.

## Design Alignment
- **Backend Pattern**: one-time data fix as a `_migrate` `from_version < 36` block that receives `blob_dir` (same as v35's `_backfill_console_cards`); writes via `.part` + `os.replace` (#734); hashes stay envelope-free (`_payload_sha256`, #734).
- **Recommendations**: scope cuts recorded in handoff section 2 (no `/health` gate, no single packer).

## Steps
- [ ] 1. Shared converter `_envelope_legacy(data, states) -> bytes` in `src/server/sync_client.py`, beside `_pack_envelope`/`_unpack_envelope`. Enveloped input returned unchanged. `states=True`: valid gzip tar -> `_FMT_TARGZ`, else `_FMT_RAW` (mirrors `_extract_state_folder`'s legacy branch). `states=False`: opens as tar via `r:*` -> `_FMT_TARGZ` when it starts with gzip magic `\x1f\x8b`, else `_FMT_TAR`; not a tar -> `_FMT_RAW` (mirrors `_write_memcard`'s legacy branch). Plus `_envelope_file_in_place(path, states) -> bool` in `src/server/store/blobs.py`: reads the file, returns False if already enveloped, else writes `<path>.part` and `os.replace`s; returns True.
  - Files: src/server/sync_client.py, src/server/store/blobs.py
  - Reuses: `_pack_envelope`, `_unpack_envelope`, `_ENVELOPE_MAGIC`, `tarfile.open` probe as in the existing fallbacks.
  - New: both functions - the sniff logic exists only inline in four client fallbacks that this issue deletes; it must live once, server-side.
- [ ] 2. Schema v36 migration: bump `_SCHEMA_VERSION` to 36; `if from_version < 36 and blob_dir is not None: _envelope_legacy_blobs(blob_dir)` which, for each of `saves`, `console_save_history`, `console_saves`, `switch_mods` (`states=False`) and `states` (`states=True`), calls `_envelope_file_in_place` on every regular file under `blob_dir/<table>/` (skip names ending `.part`; missing dir = skip). A file that fails to read is logged to stderr and skipped, never fails startup. DB rows untouched.
  - Files: src/server/store/schema.py
  - Reuses: `_migrate(conn, from_version, blob_dir)` hook and v35's skip-on-missing pattern; `_envelope_file_in_place`.
  - New: `_envelope_legacy_blobs` - small loop, mirrors `_backfill_console_cards`.
- [ ] 3. Wrap un-enveloped uploads (pre-#478 clients): in `api/blobs.py:_push._store_it` call `_envelope_file_in_place(tmp, states=kind is _STATE)` before `push_*_file`, and in `api/mods.py:push_switch_mod._store_it` with `states=False`, adding 5 to `size` when it returns True. The hash is unchanged (already payload-only in `_stage_upload`; mods hash is not stored).
  - Files: src/server/api/blobs.py, src/server/api/mods.py
  - Reuses: `_envelope_file_in_place`; existing `asyncio.to_thread(_store_it)` offload.
  - New: none.
- [ ] 4. Client fallbacks removed: `_require_envelope(data) -> (fmt, payload)` in `sync_client.py` raises `ValueError("server blob has no format header; update the EmuSync server (#738)")` when `_unpack_envelope` returns None fmt. Use it in `_write_memcard`, `_extract_state_folder`, `_merge_extract_state_folder` and `pull_state`'s inline file branch; delete each legacy sniff branch. Keep `_unpack_envelope` (server and the converter use it). Temp-dir swap, `.part` writes, `_safe_extract_tar`, and `.bak` behavior per mode unchanged.
  - Files: src/server/sync_client.py
  - Reuses: `_unpack_envelope`.
  - New: `_require_envelope` - one shared raise instead of four.
- [ ] 5. Tests (real files, real SQLite; see Testing).
- [ ] 6. Docs: CLAUDE.md Saves/sync envelope rule ("keep un-enveloped fallbacks for old blobs" -> server converts once in v36 and wraps old uploads; client raises on missing envelope; update server before clients). GOTCHAS.md #478 entry: replace "fallbacks are load-bearing, keep them" with the v36 conversion and rollout order. ARCHITECTURE.md: envelope section mention of v36 conversion.

## Checklist
Schema bump: yes (v36, data-only, no DDL). New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: yes (stored blob files rewritten once, hashes unchanged).

## Not in this plan
- `/health` `blob_format` gate (the client raise is the gate).
- Single packer (`memcard_bytes` deterministic tar vs `push_state` real-mtime tar.gz; merging risks hash churn).
- Merging the three extract functions into one `_write_blob(mode)`: their modes stay distinct; only fallbacks go.

## Log
- 2026-11-16 bplan: plan written
