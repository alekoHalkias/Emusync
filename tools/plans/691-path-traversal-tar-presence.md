# Plan: #691 Fix path traversal, unsafe tar extraction and presence monitor NameError

Issue: #691
Branch: feature/691-path-traversal-tar-presence
PR: none
Status: implementing
Fix attempts: 0

## Goal
Make ROM transfer staging, server-side memcard tar extraction and the presence monitor safe and non-crashing.

## Design Alignment
- **Backend Pattern**: errors are `HTTPException` with a short sentence; extraction reuses the existing `_safe_extract_tar` in `server/sync_client.py` (imported, not edited, to avoid conflicts with #692/#693).
- **Recommendations**: none

## Steps
- [ ] 1. `create_rom_transfer`: reduce `X-Filename` to a basename and return 400 when empty/`.`/`..`; staged file always lands in `rom_staging/<id>/`. Use `PurePosixPath(x_filename.replace("\\", "/")).name`; keep the `"rom"` default when the header is absent or blank, and validate before `mkdir` so nothing is created on rejection.
  - Files: src/server/api/transfers.py
  - Reuses: existing HTTPException pattern, `Path` already imported
  - New: none (3-line inline check; no helper needed, single caller)
- [ ] 2. `_extract_memcard_archive`: replace `tf.extractall(tmp)` with `_safe_extract_tar(tf, tmp)` (lazy `from server.sync_client import _safe_extract_tar` inside the method; blobs.py does not currently import sync_client).
  - Files: src/server/store/blobs.py
  - Reuses: server/sync_client.py:_safe_extract_tar
  - New: none
- [ ] 3. `pull_console_save_path`: delete the unreachable `dest.suffix in (".tar.gz", ".tgz")` branch (blob path `console_saves/<key>` has no suffix, so it never ran, and it called raw `extractall`). Function then just returns `(dest, meta)`.
  - Files: src/server/store/blobs.py
  - Reuses: n/a (deletion)
  - New: none
- [ ] 4. `_monitor_presence`: indent the "lock released" `_print_activity(...)` into the `for slug in _store.release_device_locks(...)` loop (fix its mis-indented continuation lines) so no unbound `slug`, one log per released lock, and later devices are still processed.
  - Files: src/server/api/_core.py (only the `_monitor_presence` body; #693 edits device-name logging and #692 CORS/PIN elsewhere in this file)
  - Reuses: existing `_print_activity`, `_game_label`
  - New: none
- [ ] 5. Tests (real SQLite, no mocks):
  - src/tests/test_rom_transfer.py: POST `/games/{slug}/rom-transfer` with `X-Filename: ../../x` and `/etc/passwd` -> 200, `staged_file` parent is `rom_staging/<transfer_id>` with name `x` / `passwd`, nothing written outside `tmp_path`; `X-Filename: ..` and `/` -> 400 and no staging dir created.
  - src/tests/test_console_memcard.py (or test_memcard_folder_sync.py): build a gz tar with a `../evil` member, call `Store._extract_memcard_archive(archive, dest)` and assert `tarfile.TarError` and no file outside dest; plus a valid archive extracts into dest.
  - src/tests/test_devices.py (next to the #597 test, same one-shot monitor harness): two offline devices, first holds no locks, second holds a lock; after one monitor pass the second's lock is released and its `game_stopped` event exists (regression for the NameError); also a device with two locks logs both (capture via `capsys`/`_print_activity` output).
- [ ] 6. Docs: none needed - internal hardening, no CLI/IPC/config/protocol change.

## Testing
- **Test File**: src/tests/test_rom_transfer.py, src/tests/test_console_memcard.py, src/tests/test_devices.py (extend existing files; fixtures `make_client`, `_device_auth`, the #597 one-shot monitor harness)
- **Test Cases**:
  - traversal_filename: `X-Filename: ../../x` stages as `rom_staging/<id>/x`, nothing outside data dir
  - absolute_filename: `/etc/passwd` stages as `passwd` inside staging dir
  - bad_filename: `..` and `/` -> 400, no staging dir created
  - malicious_tar: `Store._extract_memcard_archive` with `../evil` member raises TarError, no file outside dest
  - valid_tar: normal archive extracts into dest
  - monitor_no_locks: offline device with no locks then offline device with lock -> second lock released, game_stopped logged
  - monitor_two_locks: both released locks logged
- **Edge Cases**:
  - Backslash separators (`..\\x`) reduce to basename
  - Blank/absent header keeps default `rom`
  - Symlink/hardlink member in tar refused (already covered by helper)
- **Integration Points**:
  - Real SQLite Store via `api_module.init`; `pull_console_save_path` covered by existing memcard pull tests (must still pass after dead-branch removal)

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
Upload failure cleanup, size cap, device-name log sanitization (#693); CORS/PIN and restore atomicity in sync_client.py (#692).

## Log
