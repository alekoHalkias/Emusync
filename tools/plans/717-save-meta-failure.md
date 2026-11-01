# Plan: #717 Do not treat a failed save-meta lookup as no server save

Issue: #717
Branch: feature/717-save-meta-failure
PR: none
Status: implementing
Fix attempts: 0

## Goal
A failed `get_save_meta` request must not be read as "server has no save"; the run falls back to the existing offline launch path instead of pushing or overwriting.

## Design Alignment
- **Backend Pattern**: Errors are signalled by exceptions; "absent" is signalled by `None` (204). `_reconcile_save` stops converting one into the other. `run.py` already routes server-unreachable to `_run_offline`; the failure reuses that path.
- **Recommendations**: none. The `get_save_sync_baseline` swallow stays (None baseline is the documented conservative fallback, #460).

## Steps
- [x] 1. In `_reconcile_save`, remove the two `try/except Exception: meta = None` around `get_save_meta` so request errors propagate; a 204 still yields `None`.
  - Files: src/cli/run_reconcile.py
  - Reuses: existing `get_save_meta` 204 -> None contract (sync_client.py, run_ps2.py `_MemcardClient`)
  - New: none
- [ ] 2. In `run_game`, wrap the `_reconcile_save(...)` call: on `httpx.HTTPError`, warn on stderr, release the lock, and call `_run_offline(cfg, game_slug, game_pid_file, command)` so the game launches with no push or pull; the next online run reconciles by newest-wins.
  - Files: src/cli/run.py
  - Reuses: cli/run_offline.py `_run_offline`, `_release`, existing offline warning text
  - New: none - one try/except around an existing call
- [ ] 3. Tests: extend `_FakeClient` in src/tests/test_run_reconcile.py so a `meta` that is an Exception instance is raised from `get_save_meta`; add the cases listed under Testing. Update any existing test relying on the swallow.
  - Files: src/tests/test_run_reconcile.py
  - Reuses: `_FakeClient`, `_write_save`, `live_server` fixture (conftest.py), real SyncClient
  - New: three test functions - no existing test covers a failing meta lookup
- [ ] 4. Docs: add a one-line rule to CLAUDE.md Saves/sync ("failed save-meta lookup is never treated as no save; run falls back offline, #717").

## Testing
- **Test File**: src/tests/test_run_reconcile.py
- **Test Cases**:
  - meta_error_propagates: `_FakeClient(ReadTimeout)` with a local save -> `_reconcile_save` raises, `pushed` and `pulled` stay False (regression for #717 case A).
  - meta_204_still_pushes: `_FakeClient(None)` with a local save -> pushes (existing `no_conflict_logged_when_not_diverged` already covers; keep as the unchanged-204 guard).
  - server_save_survives_meta_failure: `live_server` with a real SyncClient subclass whose `get_save_meta` raises; push a save, call `_reconcile_save` with an older local file, assert it raises and the server's save hash is unchanged.
  - run_game_falls_back_offline: monkeypatch `cli.run._reconcile_save` to raise `httpx.ReadTimeout` and `cli.run._run_offline` to record its call; invoke `run_game` through CliRunner against `live_server`; assert `_run_offline` was called and no save was pushed.
- **Edge Cases**:
  - HTTP 5xx (`httpx.HTTPStatusError`) behaves like a timeout.
  - No-`save_path` branch (Switch first launch) also propagates instead of returning None.
  - Shared-memcard path via `_MemcardClient.get_save_meta` propagates the same way.
- **Integration Points**: `cli/run.py` try/except around `_reconcile_save` -> `_run_offline`; lock released by `_release`/finally.

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
cli/sync.py status and cli/watch.py `_save_meta` (display-only / already conservative: watcher treats None as unknown and re-checks); #718 raw-write mismatch.

## Log
