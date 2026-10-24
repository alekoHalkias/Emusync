# Plan: #597 Fix race conditions and potential SQLite contention in presence monitor

Issue: #597
Branch: feature/597-fix-presence-monitor
PR: #598
Status: shipped
Fix attempts: 0

## Goal
Synchronize the `_monitor_presence` background thread with presence updates to prevent race conditions and SQLite contention.

## Steps
- [x] 1. Wrap `_monitor_presence` logic in `_presence_lock` to ensure atomicity with `_auth` presence updates.
  - Files: `server/api/_core.py`
  - Reuses: `_presence_lock`, `_online_devices`, `_device_names`, `_store.list_devices()`, `_store.release_device_locks()`, `_print_activity()`, `_game_label()`
  - New: None - expanding existing lock scope.
- [x] 2. Ensure `_store.release_device_locks(d.id)` and subsequent `_store.log_event` calls are within the same critical section to avoid interleaving updates.
  - Files: `server/api/_core.py`
  - Reuses: `_presence_lock`
  - New: None
- [x] 3. Tests: `tests/test_devices.py`. Add a test case that simulates concurrent presence updates and monitor sweeps to check for race conditions or SQLite contention.
- [x] 4. Docs: none needed - internal server logic change.

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan

## Log
- 2026-10-24: Nested `with _presence_lock` inside the sweep deadlocked the monitor thread (same thread, non-reentrant lock); removed the inner acquire — the outer lock already covers release/log.
- 2026-10-24: Step 3 test runs the real `_monitor_presence` for one iteration (patched sleep stops the thread) concurrently with presence updates; full `tests/test_devices.py` 20 passed.