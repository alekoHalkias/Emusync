# Plan: #750 Remove orphaned blob files and stop device removal from leaking them

Issue: #750
Branch: feature/750-orphaned-blob-files
PR: none
Status: implementing
Fix attempts: 0

## Goal
Removing a device keeps its newest save/state/card generation per owner (credited to a hidden placeholder device) with no orphaned files, and existing orphans are moved to a quarantine folder once.

## Design Alignment
- **Backend Pattern**: device re-keying reuses `merge_devices` over `_DEVICE_REFS` (#656: "add any new device-id column there"); file unlink after commit (#704); one-time data fix as a `_migrate` block with `blob_dir` (v35/v36 pattern).
- **Recommendations**: none.

## Steps
- [ ] 1. Placeholder device: `REMOVED_DEVICE_ID = "removed-device"` (name "Removed device") in `src/server/store/devices.py`; `list_devices` excludes it; `api/_core.py:_auth` returns 400 for it as `X-Device-ID`.
  - Files: src/server/store/devices.py, src/server/api/_core.py
  - Reuses: `ensure_device` (creates it on demand), existing `_auth` header validation.
  - New: the constant - nothing models "no longer paired" today and the FK requires a device row.
- [ ] 2. `remove_device(device_id)` rewritten: (a) delete this device's per-device rows: `game_devices`, `consoles`, `locks`, `rom_transfers` (from/to), `rom_pull_requests` (from/to), `save_sync_baseline`, `console_save_sync_baseline`; (b) `ensure_device(REMOVED_DEVICE_ID, ...)` then `merge_devices(device_id, REMOVED_DEVICE_ID)` re-keys everything else in `_DEVICE_REFS` (saves, states, console_save_history, console_saves, switch_mods, events, conflicts) and drops the device row in the same commit; (c) `_prune_removed_generations()`: for `saves`/`states` (owner `game_slug`) and `console_save_history` (owner `console_key`), delete placeholder rows that are not the placeholder's newest row for that owner, commit, then `_unlink_blobs` their files. A device id equal to the placeholder is a no-op. `clear_devices()` becomes `remove_device` for every device except the placeholder.
  - Files: src/server/store/devices.py (+ the prune helper in src/server/store/blobs.py next to `_prune_history`)
  - Reuses: `merge_devices`, `_DEVICE_REFS`, `_unlink_blobs`, `_blob_path`.
  - New: `_prune_removed_generations` - `_prune_history` keeps the newest N across all devices; this keeps the newest 1 for one device id.
- [ ] 3. Schema v37 quarantine: bump `_SCHEMA_VERSION` to 37; `if from_version < 37 and blob_dir is not None: _quarantine_orphan_blobs(conn, blob_dir)`. Known names: ids from `saves`, `states`, `console_save_history`; `console_key` from `console_saves`; `<title_id>/<mod_name>.tar` from `switch_mods` (same layout as `SwitchModMixin._mod_blob_path`). Each regular file under those five dirs (recursive for mods) whose relative path is not known and does not end in `.part` is moved with `os.replace` to `blob_dir/.orphaned/<table>/<relpath>`; count + bytes logged to stderr. Missing table or dir is skipped; a move error is logged and skipped. Nothing is deleted.
  - Files: src/server/store/schema.py
  - Reuses: `_migrate(conn, from_version, blob_dir)` hook, v36 walk shape.
  - New: `_quarantine_orphan_blobs` - no existing code compares blob dirs with rows.
- [ ] 4. Tests (real SQLite; see Testing): extend src/tests/test_devices.py (store-level removal, existing `test_remove_device_with_games_and_saves` / `test_clear_devices_removes_all` patterns) and add v37 cases to src/tests/test_legacy_blob_conversion.py-style new file src/tests/test_orphan_blobs.py (migration over a seeded blob_dir).
- [ ] 5. Docs: CLAUDE.md Config/paths/DB bullet on device dedupe: device removal merges into `REMOVED_DEVICE_ID`, keeps newest generation per owner, unlinks the rest; v37 quarantines orphans to `blobs/.orphaned/`. GOTCHAS.md entry (#750) with the investigation result. ARCHITECTURE.md `server/store/` row: placeholder device and `.orphaned`.

## Testing
- **Test File**: src/tests/test_devices.py (removal), src/tests/test_orphan_blobs.py (new, v37 quarantine; no existing module owns blob-dir vs row checks)
- **Test Cases**:
  - remove keeps newest per game: device A pushes 3 save generations and 2 state generations for a game, device B pushes 1 save after; remove A -> A's newest save + newest state remain, credited to `REMOVED_DEVICE_ID`; A's older rows gone and their files unlinked; B's row untouched; current save (B's) unchanged
  - remove keeps a current save pushed by the removed device: only A pushed -> after removal the game still pulls the same bytes/hash
  - console card: A pushes 2 `console_save_history` generations for PS2 -> removal succeeds (no FK error) and keeps only the newest, file of the other unlinked
  - mod pusher: A pushed a Switch mod -> removal succeeds, mod row `pushed_by` = placeholder, file intact
  - placeholder hidden: `list_devices()` never includes it after removal; `GET /devices` via `client` neither
  - `_auth` rejects `X-Device-ID: removed-device` (400)
  - clear_devices: two devices with saves -> `list_devices()` empty, saves kept (one per device per game), no orphan files (every file under blobs/saves has a row)
  - existing `test_remove_device_with_games_and_saves`, `test_clear_devices_removes_all`, `test_delete_device_endpoint_with_configured_game` still pass
  - v37: seeded blob_dir with one row-backed file and one orphan per table (saves, states, console_save_history, console_saves, nested switch_mods) plus `.uploads/x` and `saves/y.part` -> orphans moved to `.orphaned/<table>/<relpath>` byte-identical, row-backed files and `.uploads`/`.part` untouched, `user_version == 37`
  - v37 idempotent: second run moves nothing
- **Edge Cases**:
  - removing the placeholder id itself: no-op
  - removing a device twice / unknown id: no error
  - second removed device for the same game: earlier placeholder generation is pruned so only the newest placeholder generation remains (documented consequence of keep-newest)
  - v37 with a table missing (partial DB): skipped
- **Integration Points**:
  - Server PC after ship: re-run the orphan count; expect 0 outside `.orphaned`, 45 saves + 18 states files inside it; row hash audit unchanged.

## Checklist
Schema bump: yes (v37, file moves only, no DDL). New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: yes (orphan files moved once).

## Not in this plan
- Deleting `blobs/.orphaned/` (user decision: quarantine; delete manually later).
- Showing "Removed device" specially in the GUI history list.
- Pruning history beyond `HISTORY_LIMIT` for games not pushed since #565 (rows, not orphans).

## Log
- 2026-11-16 bplan: plan written
- 2026-11-16 tplan: 10 test cases + edge cases
