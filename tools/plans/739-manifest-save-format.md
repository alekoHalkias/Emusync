# Plan: #739 Replace save blob formats with a manifest payload

Issue: #739
Branch: feature/739-evaluate-manifest-format
PR: none
Status: planned
Fix attempts: 0

## Goal
Every save, state, memory card, mod and rom-folder blob travels and is stored in one format (envelope format 3: an uncompressed tar whose first member is a JSON manifest of per-file path, size and sha256). The server converts all stored blobs once, after backing up the database and keeping the original files.

## Format (decided)
- Envelope unchanged (`ES1\0` + format byte). New `_FMT_TREE = 3`. Payload = uncompressed tar.
- First tar member `.emusync-manifest.json`: `{"v": 1, "kind": "file"|"dir", "files": [{"path", "size", "sha256"}]}`, entries sorted by path.
- `kind: "file"`: exactly one entry, `path: ""`, stored as tar member `.emusync-file`. Name-independent, so the same save under different filenames on two devices hashes the same.
- `kind: "dir"`: one entry per regular file, relative POSIX path. No links or special files.
- Content hash: `file` = the file's sha256 (unchanged from today, so GUI `files:getFileHash` (`useGameSync.ts`) and every single-file baseline stay valid). `dir` = sha256 of the compact JSON of the sorted `[path, size, sha256]` list. Independent of tar framing and mtimes.
- Uncompressed: states lose gzip. ponytail: no compression; rom-folder ROMs are incompressible and gzip on multi-GB folders is slow. Add per-member compression if state storage size becomes a problem.
- `CardFormatMismatch` stays: a local folder against a server `file` manifest (or the reverse) is a layout difference, not an encoding one. The issue's acceptance criterion is corrected accordingly.

## Design Alignment
- **Backend Pattern**: one shared codec module used by client, server store, API and migration, the same way `_pack_envelope`/`_legacy_format` are shared today. Server-first rollout with a strict client check, as in #749 (`_require_envelope`). Schema-version-gated one-time file conversion, as in v36/v37 (`_envelope_legacy_blobs`, `_quarantine_orphan_blobs`). Content hashes stay envelope-free (#734), now derived from the manifest instead of skipping a header.
- **Recommendations**: the new module keeps `sync_client.py` (852 lines) from growing; the tar extraction helpers move into it and are re-exported from `sync_client`.

## Steps
- [ ] 1. Codec module `src/server/blob_tree.py`: `pack_tree(path, include=None) -> bytes` (enveloped format 3; `include(rel_path) -> bool` filter, `.bak` always skipped), `content_hash(path, include=None) -> str`, `manifest_hash(manifest) -> str`, `read_manifest(f)` (reads only the first member from a seekable file), `verify_blob(path) -> (manifest, hash)` (raises `ValueError` on missing envelope, format other than 3, bad manifest, a member missing from or not in the manifest, size/sha mismatch, link/special/absolute/`..` member), `extract_tree(data, parent) -> (kind, tmp_path)` (extract to a temp dir under *parent*, verify each file against the manifest, return the temp dir or temp file), `legacy_to_tree(fmt, payload) -> bytes` (format 0/1/2 to 3, for the migration only).
  - Files: src/server/blob_tree.py (new), src/server/sync_client.py
  - Reuses: sync_client._safe_extract_tar, _extract_tar_to_tmp (moved here, re-exported from sync_client), _ENVELOPE_MAGIC/_pack_envelope, the deterministic sorted rglob walk of _memcard_payload_bytes
  - New: blob_tree.py - the codec is needed by client, store, API and migration; putting it in sync_client.py would push that file further past the size limit
- [ ] 2. Client writes go through the manifest: `_write_memcard` dispatches on manifest kind (`file` -> `_write_memcard_raw_bytes`, keeps `CardFormatMismatch`; `dir` -> the existing backup-then-`os.replace` swap from `_write_memcard_tar_bytes`, now fed by `extract_tree`). `_extract_state_folder`, `_merge_extract_state_folder` and the single-file branch of `SyncClient.pull_state` use `extract_tree` and keep their current `.bak` rules. A `kind: "dir"` blob onto a single-file state path, or `file` onto the shared merge folder, keeps today's behavior (raise / ignore). `_require_envelope` requires format 3 and says to update the server.
  - Files: src/server/sync_client.py
  - Reuses: _write_memcard_raw_bytes, the swap block of _write_memcard_tar_bytes, _backup_state_files, the merge loop of _merge_extract_state_folder
  - New: none
- [ ] 3. Client pushes and hashes use the manifest: `memcard_bytes` -> `pack_tree`; `SyncClient.push_state` -> `pack_tree(p, include=prefix filter)`; `run_reconcile._reconcile_save` and `run.py` post-launch compare use `content_hash` instead of `sha256(_memcard_payload_bytes(...))`; delete `_memcard_payload_bytes`. The single-file state compare in run.py stays as is (same hash).
  - Files: src/server/sync_client.py, src/cli/run_reconcile.py, src/cli/run.py
  - Reuses: blob_tree.pack_tree / content_hash
  - New: none
- [ ] 4. rom-folder transfers: send path already calls `memcard_bytes` (now format 3, no change). Receive path: an enveloped blob goes to `_write_memcard`; the bare `tar -cf` from GUI `rom:push` is extracted through `_extract_tar_to_tmp` plus the same swap, declared by kind and never sniffed (#738). Drop the `_pack_envelope(_FMT_TAR, ...)` wrap.
  - Files: src/cli/transfer.py, src/server/sync_client.py (expose the swap as `_swap_folder(card, tmp)`)
  - Reuses: _extract_tar_to_tmp, the swap from step 2
  - New: none
- [ ] 5. Server upload, store and integrity: `_stage_upload` streams to disk and returns `(path, size)` with no hashing or header handling. `_push._store_it` and the mod push call `verify_blob(tmp)` and use its hash; `ValueError` -> 400 "Unsupported save format; update the EmuSync client" with the staged file removed. Drop `_envelope_file_in_place` from both upload routes (it stays for the v36 migration). `store/blobs.py` `_payload_sha256` is replaced by a `verify_blob`-based hash in `_push_blob`, `_classify_blob` (a verify failure counts as `hash_mismatch`) and `_last_good_version`.
  - Files: src/server/api/blobs.py, src/server/api/mods.py, src/server/store/blobs.py
  - Reuses: blob_tree.verify_blob, existing 400/staging-cleanup pattern (#701/#704/#715)
  - New: none
- [ ] 6. Schema v38 one-time conversion `_convert_blobs_to_tree(conn, blob_dir)` in schema.py, after v37: (a) back up the DB with `conn.backup` to `<data_dir>/emusync.db.pre-v38` (skip if present); (b) for each file in `saves`, `states`, `console_save_history`, `switch_mods` (not the retired `console_saves`, not `.part`, `.orphaned`, `.uploads`): skip format 3; otherwise `legacy_to_tree` -> `<file>.part` -> `verify_blob` -> move the original to `blobs/.pre-v38/<table>/<rel>` -> `os.replace` the `.part` in; (c) update each converted row's `size`, and for `dir` blobs its `hash`, building an old->new hash map per owner; (d) remap `save_sync_baseline`, `console_save_sync_baseline` and the winner/loser hashes in `save_conflicts`/`console_save_conflicts` with that map. Idempotent, a failed file is reported on stderr and left as is (never fails startup), totals printed. Bump `_SCHEMA_VERSION` to 38.
  - Files: src/server/store/schema.py
  - Reuses: the v36/v37 loop shape (`_envelope_legacy_blobs`, `_quarantine_orphan_blobs`), blob_tree.legacy_to_tree / verify_blob, `.part` + `os.replace` (#734)
  - New: none
- [ ] 7. Tests (no mocks, real SQLite). First `src/tests/conftest.py`: add `tree(data: bytes) -> bytes` (a `kind: "file"` blob via `blob_tree.pack_tree` on a tmp file) and make `raw_env(data)` return it, so the about 70 raw-byte posts and 37 `store.push_*` calls are wrapped mechanically (`content=tree(b"...")`) and the pulled-body asserts keep using `raw_env`. Then new `src/tests/test_blob_tree.py` (file and dir round trip, file hash equals plain sha256 and ignores filename, dir hash ignores mtimes and tar order, `.bak` and prefix filter, tampered member / extra member / `..` member / symlink rejected, `CardFormatMismatch` still raised, format 0/1/2 upload -> 400 and nothing stored, mod upload same); new `src/tests/test_tree_migration.py` (v37 DB with raw, tar and tar.gz blobs plus baselines and conflicts -> v38: every blob is format 3 and extracts to the original content, dir hashes and baselines remapped together so `_reconcile_save` sees no divergence, single-file hashes unchanged, originals in `.pre-v38`, DB backup exists, second run is a no-op, an unreadable file is skipped). Update the existing tests that build `_FMT_*` blobs or call `_memcard_payload_bytes`: test_console_memcard, test_integrity, test_legacy_blob_conversion, test_memcard_folder_sync, test_new_consoles, test_restore_safety, test_run_reconcile, test_saves, test_state_sync, test_wii_save_sync.
  - Files: src/tests/*
  - Reuses: test_integration.py `client` fixture and AUTH headers, test_legacy_blob_conversion.py DB setup
  - New: two test files - no existing file covers the codec or the v38 migration
- [ ] 8. Docs: CLAUDE.md Saves/sync envelope bullet (format 3 only; hash rule; server-first rollout; `.pre-v38` and `emusync.db.pre-v38` can be deleted by hand once synced), GOTCHAS.md manifest section with the hash-stability reasoning, ARCHITECTURE.md envelope section; backend design guide hash line.
  - Files: CLAUDE.md, src/docs/GOTCHAS.md, src/docs/ARCHITECTURE.md, .claude/backend-design-guide.md
  - Reuses: existing sections (#478, #738, #734 entries)
  - New: none

## Testing
- **Test File**: src/tests/test_blob_tree.py (codec + API), src/tests/test_tree_migration.py (v38); helper in src/tests/conftest.py; existing suites updated in place.
- **Test Cases**:
  - file round trip: pack_tree on a file -> extract_tree -> same bytes; content_hash == hashlib.sha256(bytes).
  - file hash ignores filename: same bytes under two names -> same hash.
  - dir round trip: nested folder (PCSX2-style `GAME1/GAME1`) -> extract -> identical tree; content_hash equal before and after.
  - deterministic pack: pack_tree twice (touching mtimes between) -> identical bytes and hash.
  - filters: `.bak` never packed; push_state prefix filter packs only matching names.
  - push/pull API: format 3 save, state and card push -> 200, recorded hash == content_hash; pull returns the stored bytes.
  - format 0/1/2 and un-enveloped uploads -> 400 on save, state, card and mod routes; nothing stored, staged file removed.
  - CardFormatMismatch: `file` blob onto a local folder raises; `_reconcile_save` local-wins path still pushes and reports (existing test_run_reconcile case, now on format 3).
  - migration: v37 DB seeded with raw save, tar card, tar.gz state, tar mod, plus baselines and conflicts -> v38: every file format 3, extracts to original content, dir row hashes and baselines remapped together, single-file hashes unchanged, size updated, originals under `blobs/.pre-v38/`, `emusync.db.pre-v38` exists.
  - migration idempotent: second `_migrate(..., from_version=37)` leaves every file and row unchanged.
- **Edge Cases**:
  - tampered blob: member bytes changed / member added / member missing vs manifest -> verify_blob raises; extract_tree leaves the target untouched.
  - hostile members: `..`, absolute path, symlink, device -> rejected (reuses _safe_extract_tar).
  - empty folder save -> `dir` with zero files round-trips; empty upload still 400 (#715).
  - integrity: a tampered stored blob classifies as damaged (`hash_mismatch`) and last_good skips it.
  - migration: unreadable or already-format-3 file skipped with stderr note, startup does not fail; stray `.part`, `.orphaned/`, `.uploads/` and `console_saves/` untouched.
  - restore: restoring a pre-conversion generation after v38 yields a format 3 blob with the remapped hash.
- **Integration Points**:
  - SyncClient against `live_server`: device A pushes a folder card, device B pulls it, files equal and `_reconcile_save` reports no divergence (extend test_memcard_folder_sync).
  - rom-folder transfer: enveloped send path and bare `tar -cf` receive path both land the folder (extend test_rom_transfer).
  - GUI `files:getFileHash` relies on single-file hash == sha256(file); covered by the file hash case, no JS test runner.

## Checklist
Schema bump: yes (v38, file conversion and hash remap, no column change). New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: yes (`blobs/.pre-v38/`, `emusync.db.pre-v38`).

## Rollout
Breaking. Update the server first (the conversion runs on startup), then every client. Before updating, an old client fails pulls with a missing-format error and pushes with 400. Accepted: one user, three self-managed devices.

## Not in this plan
- Phase E table merge (dropped, see the issue).
- Per-file conflict view, delta transfer, compression: the manifest enables them, nobody has asked for them.
- Removing `CardFormatMismatch`: not possible, see Format.
- Automatic deletion of `.pre-v38` originals.

## Log
- 2026-11-20 bplan: plan written
