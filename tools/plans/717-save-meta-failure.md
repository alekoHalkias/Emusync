# Plan: #717 Do not treat a failed save-meta lookup as no server save

Issue: #717
Branch: feature/717-save-meta-failure
PR: none
Status: planned
Fix attempts: 0

## Goal
A failed `get_save_meta` request must not be read as "server has no save"; the run falls back to the existing offline launch path instead of pushing or overwriting.

## Design Alignment
- **Backend Pattern**: Errors are signalled by exceptions; "absent" is signalled by `None` (204). `_reconcile_save` stops converting one into the other. `run.py` already routes server-unreachable to `_run_offline`; the failure reuses that path.
- **Recommendations**: none. The `get_save_sync_baseline` swallow stays (None baseline is the documented conservative fallback, #460).

## Steps
- [ ] 1. In `_reconcile_save`, remove the two `try/except Exception: meta = None` around `get_save_meta` so request errors propagate; a 204 still yields `None`.
  - Files: src/cli/run_reconcile.py
  - Reuses: existing `get_save_meta` 204 -> None contract (sync_client.py, run_ps2.py `_MemcardClient`)
  - New: none
- [ ] 2. In `run_game`, wrap the `_reconcile_save(...)` call: on `httpx.HTTPError`, warn on stderr, release the lock, and call `_run_offline(cfg, game_slug, game_pid_file, command)` so the game launches with no push or pull; the next online run reconciles by newest-wins.
  - Files: src/cli/run.py
  - Reuses: cli/run_offline.py `_run_offline`, `_release`, existing offline warning text
  - New: none - one try/except around an existing call
- [ ] 3. Tests (src/tests/test_run_reconcile.py): meta raises -> `_reconcile_save` raises and pushes nothing; meta 204 with local save still pushes; run-level case where reconcile fails leaves the existing server save as current (real SQLite server via existing fixtures, failure injected by pointing meta at a closed port or a client subclass overriding only `get_save_meta`). Update any existing test relying on the swallow.
- [ ] 4. Docs: add a one-line rule to CLAUDE.md Saves/sync ("failed save-meta lookup is never treated as no save; run falls back offline, #717").

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
cli/sync.py status and cli/watch.py `_save_meta` (display-only / already conservative: watcher treats None as unknown and re-checks); #718 raw-write mismatch.

## Log
