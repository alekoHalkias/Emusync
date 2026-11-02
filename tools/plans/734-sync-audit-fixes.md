# Plan: #734 Fix save integrity hashing, reconcile baseline, stale locks and related sync issues

Issue: #734
Branch: feature/734-sync-audit-fixes
PR: #735
Status: shipped
Fix attempts: 0

## Goal
Make server-side hashes envelope-free everywhere, drive pre-launch push/pull from the sync baseline, honour the lock TTL on reads, and close the smaller sync robustness gaps from the audit.

## Design Alignment
- **Backend Pattern**: Fixes stay inside existing Store mixins (`store/blobs.py`, `store/locks.py`), the existing reconcile policy function, and existing SyncClient methods. No new routes, tables, schema bump or config. Post-commit unlinking follows the #704 rule already used by `_push_blob_file`.
- **Recommendations**: Add to the design guide: "Server-side content hashes are always envelope-free (`_payload_sha256`); never `hashlib.sha256(file_bytes)` on a stored blob."

Overlap note: open PR #733 (#731) edits `cli/run.py` (launch-command / relocation hunks near the top and ~line 265) and `server/sync_client.py` (GameDeviceConfig, ~362-432). This plan's edits are in other regions (state pull block, lines 311-330, push_state, memcard writers), so no textual conflict is expected.

## Steps
- [x] 1. Envelope-free hash helper used by integrity, last-good, restore and console restore. An enveloped push reports `ok`; a restored generation's hash equals the client's content hash.
  - Files: src/server/store/blobs.py
  - Reuses: server/sync_client.py:_ENVELOPE_MAGIC, _ENVELOPE_HEADER_LEN (already imported by api/blobs.py); same stripping rule as api/blobs.py:_stage_upload.
  - New: module-level `_payload_sha256(data: bytes) -> str` (strip header only when the magic is present) - no existing helper hashes stored bytes envelope-free. Use it in `_push_blob` (covers `_restore_blob` and `push_save(data)`), `_classify_blob`, `_last_good_version`, `restore_console_save`.
- [x] 2. Baseline-driven pre-launch reconcile. With a baseline: local unchanged and server changed -> pull; local changed and server unchanged -> push; mtime only breaks true divergence. No baseline keeps current behaviour.
  - Files: src/cli/run_reconcile.py
  - Reuses: `_decide_save_action` (add optional `baseline_hash: Optional[str] = None` param so existing tests/callers keep working); `_reconcile_save` passes the baseline hash it already fetches.
  - New: none.
- [x] 3. Locks: expired locks read as unlocked and acquire is atomic.
  - Files: src/server/store/locks.py, src/server/store/games.py
  - Reuses: `LOCK_TTL_HOURS`; existing `locks` PRIMARY KEY on game_slug.
  - Change: `get_lock` returns None when `acquired_at` is older than the TTL (covers API, cli/sync.py, cli/watch.py, cli/run.py). `acquire_lock` becomes one `INSERT ... ON CONFLICT(game_slug) DO UPDATE ... WHERE locks.device_id = excluded.device_id OR locks.acquired_at < :cutoff`, then re-reads the holder and raises ValueError if it is not the caller. games.py overview `LEFT JOIN locks` adds `AND l.acquired_at >= :cutoff` so an expired lock doesn't show as running.
  - New: small `_lock_cutoff()` helper in locks.py returning the ISO cutoff - shared by get_lock, acquire_lock and the overview query.
- [x] 4. Failed state pull no longer blocks launch.
  - Files: src/cli/run.py (state pull block only)
  - Reuses: existing warning style from the #717 save fallback.
  - Change: wrap `pull_state` / `pull_state_merge` in `try/except Exception`; on failure warn on stderr and clear the local `state_path` used for the post-game state push, so a stale local state is never pushed over a server state this device could not read.
  - New: none.
- [x] 5. SyncClient cleanup: remove the dead first `pull_save`/`push_save` copies; `push_state` folder pack recurses (`rglob`, arcname relative posix path, skip `.bak`, `name_prefix` matched on basename); `_backup_state_files` backs up nested files too, so nested pulls keep a `.bak`.
  - Files: src/server/sync_client.py
  - Reuses: `_memcard_payload_bytes` rglob/relative-path pattern.
  - New: none.
- [x] 6. Raw save writes are atomic and never silently skipped. `_write_memcard_raw_bytes` writes to a sibling `.part` then `os.replace`; if the target is a directory it raises ValueError instead of returning (so `pull_save` does not report pulled=True).
  - Files: src/server/sync_client.py
  - Reuses: `.part` + `os.replace` pattern from `download_transfer`.
  - New: none.
- [x] 7. Console memcard store: history files unlinked only after commit; pulls stream an immutable history file instead of the live slot.
  - Files: src/server/store/blobs.py
  - Reuses: `_prune_history` (returns stale ids, caller unlinks after commit) shape; `_unlink_blobs`.
  - Change: `_prune_console_history` returns stale ids; `_push_console_history_row` returns them; `push_console_save_file` unlinks them after `commit()`. `pull_console_save_path` returns the newest `console_save_history` file whose hash equals the live `console_saves.hash` (falls back to the live `console_saves/<key>` path for cards with no matching history, e.g. pre-#480).
  - New: none.
- [x] 8. Tests (no mocks, real SQLite):
  - tests/test_integrity.py: enveloped push via API reports `ok`; restore returns a hash equal to sha256(payload); last-good found for enveloped blobs.
  - tests/test_console_memcard.py: console restore hash envelope-free; pull after push returns content matching hash; history unlink after prune.
  - tests/test_run_reconcile.py: `_decide_save_action` with baseline: local==baseline, server changed, local mtime newer -> pull; local changed, server==baseline, local mtime older -> push; diverged keeps mtime rule.
  - tests/test_locks.py: expired lock reads as unlocked via API; acquire by another device succeeds after TTL; same-device refresh still works; held fresh lock still 409.
  - tests/test_state_sync.py: push_state folder includes subfolder files and skips `.bak`.
  - tests/test_memcard_folder_sync.py (or test_state_sync.py): raw pull onto a directory raises; raw write leaves no `.part`.
- [x] 9. Docs: GOTCHAS.md entry for server-side envelope-free hashing (#734) and lock TTL on read; one-line CLAUDE.md rule under Saves/sync; design guide line from Design Alignment. ARCHITECTURE.md: none needed - no new routes, IPC, CLI or config.

## Testing
- **Test Files**: src/tests/test_integrity.py, test_console_memcard.py, test_run_reconcile.py, test_locks.py, test_state_sync.py (all existing; extend, no new files)
- **Test Cases**:
  - integrity_ok_for_enveloped_save: `store.push_save(_pack_envelope(_FMT_RAW, payload))` -> `integrity_for_game` status ok, hash == sha256(payload); reuses test_integrity Store pattern.
  - last_good_finds_enveloped_version: corrupt current via existing `_corrupt_current`, last_good points at the enveloped prior.
  - restore_hash_is_envelope_free: push two enveloped versions, `restore_save(v1)` hash == sha256(payload1).
  - console_restore_hash_is_envelope_free: same for `restore_console_save`.
  - console_pull_serves_history_copy: after push, `pull_console_save_path` path content hashes to meta hash and is not the live slot; legacy card (live row, no history) falls back to live path.
  - console_prune_unlinks_after_commit: push HISTORY_LIMIT+1 cards, oldest history file gone, row count == HISTORY_LIMIT.
  - decide_pull_when_only_server_changed: baseline == local, server differs, local mtime LATER -> pull.
  - decide_push_when_only_local_changed: server == baseline, local differs, local mtime EARLIER -> push.
  - decide_diverged_uses_mtime: both differ from baseline -> existing mtime rule.
  - expired_lock_reads_unlocked: backdate `acquired_at` past LOCK_TTL_HOURS via `store._conn`, GET /games/{slug}/lock -> locked false; overview lock_device_id None.
  - other_device_acquires_expired_lock / fresh_lock_still_409 / same_device_refresh_ok via `_device_auth`.
  - push_state_folder_includes_subfolders: nested file packed with relative arcname, `.bak` skipped, `name_prefix` matches basename; round-trip through `_extract_state_folder`.
  - raw_write_atomic_and_dir_guard: `_write_memcard_raw_bytes` leaves no `.part`, keeps `.bak`; directory target raises ValueError.
- **Edge Cases**:
  - Legacy un-enveloped blob still hashes to sha256(full bytes) (existing test_integrity cases keep passing unchanged).
  - Lock exactly at the cutoff; naive legacy `acquired_at` string.
  - No baseline -> unchanged mtime behaviour (existing test_run_reconcile cases).
- **Integration Points**:
  - api/blobs.py:_stage_upload hash must equal `_payload_sha256` for the same bytes (assert in integrity test via API push).
  - cli/run.py state pull failure: covered by a run_game test in test_run_reconcile.py using an unreachable/500 state route if an existing live_server pattern there fits; otherwise noted in PR as manual.

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
- Rewriting stored hashes of previously restored generations (clients converge after one re-push).
- Locks race beyond the single-statement upsert (no multi-process server).

## Log
- 2026-11-02 bplan: plan written
- 2026-11-02 tplan: testing section added
Step 4: used a state_pull_failed flag instead of clearing state_path, so the post-game path-adoption PUT never blanks the stored state path.
Step 6: dropped the directory-target raise. test_memcard_folder_sync.py::test_write_memcard_legacy_fallback_does_not_crash_on_directory_target requires the skip on purpose (folder-card device receiving an old flat-file blob must not crash; its post-game push migrates the server). Atomic .part write kept.
