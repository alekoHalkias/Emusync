# Plan: #725 Link Switch game saves for Pokemon Legends Z-A across Steam Deck and Arch

Issue: #725
Branch: feature/725-switch-legends-za-save-link
PR: none
Status: planned
Fix attempts: 0

## Goal
(a) A Switch game whose device already has a learned save folder publishes its title ID to the server, so other devices can match and seed the same save. (b) The post-game push/release runs in a detached background process so quitting the game from Steam returns immediately and Steam cannot cut the push short.

## Design Alignment
- **Backend Pattern**: CLI run path (`cli/run.py`) already backfills `switch_title_id` via `client.update_game` in two places (#443): after a title-ID local match, and after a post-launch adoption. Both are skipped when `save_path` is already set on the device and the server ID is blank (game played before the self-heal existed, or save path set manually). That is the confirmed code gap: the other device then has no ID to match or seed from, so saves never link. Fix at the shared point in `run_game`, before reconcile, reusing `update_game`.
- **Recommendations**: Root cause on the user's Deck/Arch data is not observed (the local DB here has no Z-A row). The fix covers the gap found in code; if the stored ID is non-blank but wrong, that is a separate follow-up.

## Steps
- [ ] 1. In `run_switch.py` add `_switch_title_id_from_save_path(save_path)`: returns the folder basename if it matches the 16-hex title ID regex, else "".
  - Files: src/cli/run_switch.py
  - Reuses: `_SWITCH_TITLE_ID_RE` pattern in src/cli/detect.py (bracket-free variant needed)
  - New: one small helper - existing `_switch_title_id_from_rom` parses a bracketed filename tag, not a folder name.
- [ ] 2. In `run_game` (after `resolved_title_id`/before reconcile), when `console_abbr == "Switch"` and `not switch_title_id` and `save_path` is set: derive the ID from `save_path` (fall back to `resolved_title_id`), call `client.update_game(game_slug, game_name, switch_title_id=...)` inside try/except warning, and set `switch_title_id`/`resolved_title_id`.
  - Files: src/cli/run.py
  - Reuses: `client.update_game`, the existing warning pattern at run.py:387
  - New: none
- [ ] 3. Detach the post-game work (user idea). Add `_detach_after_game(log_path) -> None` in `run_offline.py` (POSIX only): `os.fork()`; the parent flushes and `os._exit(exit_code)` at once (skipping the `finally`, so it neither releases the lock nor deletes the pid file); the child calls `os.setsid()`, ignores SIGHUP, redirects stdin/stdout/stderr to `<data_dir>/launch.log` (append) so Steam holds no pipe open, and carries on through the existing detection, push, `_release()` and pid-file cleanup unchanged. Call it in `run_game` right after `stop_heartbeat.set()` following `_launch_and_wait`. Add a `--detach/--no-detach` Click option (default on) with Python default `detach=False` on the function, so the existing tests that call `run_game.callback(game_slug=..., command=...)` never fork. Windows (no `os.fork`) falls back to the current inline behaviour.
  - Files: src/cli/run.py, src/cli/run_offline.py
  - Reuses: existing post-launch block, `_release()` finally path, `_run_offline_mod` module, launch.log in data_dir
  - New: `_detach_after_game` - no existing fork or daemonize helper in the codebase; fork keeps all in-memory state (clients, hashes, launch_start) so no new subcommand or argument plumbing is needed.
  - Known limits: lock heartbeat is stopped before the fork, so a very long push is covered only by the lock TTL (hours); a relaunch during the background push is blocked by the still-held lock, which is the intended protection; if Steam/systemd kills the whole cgroup, setsid alone cannot survive it.
- [ ] 4. Tests: src/tests/test_switch_save_sync.py - helper returns ID for a 16-hex folder and "" otherwise; run with `save_path` set and blank server ID backfills the ID (real SQLite, existing fixtures in that file); no backfill when ID already stored. No mocks.
- [ ] 5. Docs: GOTCHAS.md: one line on the Switch backfill; a "post-game push is detached (#725)" note (fork+setsid, tests use detach=False, Windows inline); CLAUDE.md Saves/sync rules one line.

## Testing
- **Test File**: src/tests/test_switch_save_sync.py (helper cases); src/tests/test_run_reconcile.py (run_game backfill, reusing its existing run_game harness)
- **Test Cases**:
  - detach: run a tiny script via subprocess that calls `_detach_after_game`, assert the parent exits promptly with the given code while the child writes a marker file afterwards (real fork, no mocks); skipped on Windows
  - helper returns the ID for a 16-hex folder path
  - run_game with save_path set and blank server title ID calls update_game with the ID
  - no update when server ID already stored
- **Edge Cases**:
  - non-hex folder name (e.g. a path ending in a game name) returns "" and nothing is stored
  - update_game failure only warns, launch continues
- **Integration Points**: client.update_game -> PUT /games/{slug} -> store.update_game_switch_title_id

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
Correcting a wrong stored title ID; titledb fuzzy matching; additional Eden roots.

## Log
