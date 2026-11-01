# Plan: #699 Harden run signal handling, tar extraction and transfer timeouts

Status: implementing

## Backend plan
1. cli/run.py: register `_sigterm_handler` for SIGHUP and SIGINT as well (kill child, return; no sys.exit, per #472). Create `stop_heartbeat` before the main try and set it in the outer `finally` so any pre-launch exception stops the heartbeat; the finally already releases the lock.
2. server/sync_client.py `_safe_extract_tar`: keep the path/link checks; then `extractall(filter="data")` when `hasattr(tarfile, "data_filter")`, else reject non-regular/non-dir members and clear setuid/setgid/sticky bits.
3. server/sync_client.py: add `_TRANSFER_TIMEOUT = httpx.Timeout(10, read=600, write=600)`; use it for whole-blob save/state/memcard/mod calls. Health, lock and metadata calls keep short timeouts; #458 retries untouched.

## Testing plan
- src/tests/test_run_safety.py: `_safe_extract_tar` rejects a FIFO member and strips setuid on a real tar; SIGHUP/SIGINT handlers are `_sigterm_handler`; transfer timeout read >= 300.

## Steps
- [ ] 1 run.py signals + heartbeat cleanup
- [ ] 2 _safe_extract_tar
- [ ] 3 transfer timeouts
- [ ] 4 tests
- [ ] 5 GOTCHAS note
