# Plan: #704 Harden server blob store, presence monitor and upload limits

Issue: #704
Branch: feature/704-server-robustness
PR: none
Status: implementing
Fix attempts: 0

## Goal
Fix five server robustness defects with the smallest backend diff.

## Design Alignment
- Backend Pattern: validation at the API boundary as HTTPException; module-level constant cap like `transfers._MAX_UPLOAD_BYTES` (#693); store logic stays in mixins.
- No schema, config, IPC or CLI change.

## Steps
- [x] 1. `store/blobs.py`: `_push_blob_file` moves the file into place first (`os.replace`), then inserts the row, prunes rows and commits; on any exception `rollback()` and unlink the placed file. `_prune_history` returns stale ids and deletes rows only; callers unlink the stale files after `commit()` (also in `_push_blob`).
- [x] 2. `api/_core.py` `_monitor_presence`: snapshot `list_devices()` and `_online_devices` outside the lock, per-device try/except, treat naive `last_seen_at` as UTC, take `_presence_lock` only for set/dict mutation; DB calls (`release_device_locks`, `log_event`) outside the lock.
- [x] 3. `api/blobs.py` `_stage_upload`: module constant `_MAX_UPLOAD_BYTES` (4 GiB, ponytail: fixed ceiling); over cap raises 413 (tmp already removed by the existing `except BaseException`). Also remove tmp if `_store_it` raises in `_push` and `push_console_memcard`.
- [x] 4. `api/transfers.py` `create_pull_request`: take `request_body: Any = Body(...)`; non-dict -> 400; `kind` must be in `{"rom", "network-upload"}` -> 400.
- [x] 5. `store/blobs.py` `_archive_memcard_folder`: `tarfile.open(tmp, "w:gz")` directly to the temp file; hash and size from the file in 1 MiB chunks.
- [x] 6. Tests: `src/tests/test_hardening_704.py`, one per step.

## Test Plan
- failed `os.replace` leaves no row and later commit does not resurrect it; pruned file survives a failed commit path is covered by order (unlink after commit).
- monitor: extract the per-iteration body into `_presence_tick()` so it can be called directly; a device with a naive/garbage `last_seen_at` does not prevent another stale device from going offline.
- upload over cap -> 413, `.uploads` empty.
- pull request with list body / bad kind -> 400.
- `_archive_memcard_folder` on a folder returns matching hash/size of the file and extracts.
