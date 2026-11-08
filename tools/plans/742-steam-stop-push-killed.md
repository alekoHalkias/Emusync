# Plan: #742 Save push is killed when a Steam-launched game is stopped from the GUI

Issue: #742
Branch: feature/742-steam-stop-push-killed
PR: none
Status: implementing
Fix attempts: 0

## Goal
Move the detached post-game child into its own systemd user scope so Steam tearing down the game's cgroup/process tree cannot kill the push.

## Design Alignment
- **Backend Pattern**: extends the #725 `_detach_after_game` in `run_offline.py`; best-effort OS helper, silent fallback to current behavior (same style as the other optional-tool fallbacks).
- **Recommendations**: none. Rejected: re-exec of the whole run in a scope (also moves the emulator out of Steam's cleanup); delaying parent exit (undoes #725).

## Steps
- [x] 1. Add `_escape_steam_scope()` to `run_offline.py`; call it in the child of `_detach_after_game` right after `os.setsid()`. It runs `busctl --user call org.freedesktop.systemd1 /org/freedesktop/systemd1 org.freedesktop.systemd1.Manager StartTransientUnit ssa(sv)a(sa(sv)) emusync-push-<pid>.scope fail 1 PIDs au 1 <pid> 0` with a short timeout; all failures (no busctl, no user bus, non-systemd, Windows) are swallowed so the fork-only behavior remains. Leave the `ponytail:` note in the docstring updated.
  - Files: src/cli/run_offline.py
  - Reuses: `_detach_after_game` (existing fork/setsid child path), stdlib `subprocess`/`shutil.which`
  - New: `_escape_steam_scope` - no existing helper talks to systemd
- [x] 2. Tests: extend `src/tests/test_run_detach.py`: (a) helper is a no-op returning cleanly with `PATH` lacking busctl; (b) skipif no user bus: after the call `/proc/self/cgroup` of the child differs from before. Existing fork test must still pass.
  - Files: src/tests/test_run_detach.py
  - Reuses: its subprocess-based fork pattern
  - New: none
- [x] 3. Docs: update the #725 paragraph in src/docs/GOTCHAS.md (scope escape added, limit "setsid does not survive a cgroup-wide kill" now conditional on systemd) and the #725 bullet in CLAUDE.md.
  - Files: src/docs/GOTCHAS.md, CLAUDE.md
  - Reuses: existing #725 text
  - New: none

## Testing
- **Test File**: src/tests/test_run_detach.py (extends the existing real-fork subprocess test)
- **Test Cases**:
  - no_busctl: `_escape_steam_scope()` returns without raising when PATH has no busctl
  - scope_escape: child's /proc/self/cgroup differs after the call (skipif no user bus)
  - existing fork test still passes
- **Edge Cases**:
  - busctl present but user bus unreachable: swallowed, push continues
- **Integration Points**:
  - `_detach_after_game` child path; run_game's push/release unchanged

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
- Cleaning the stale `.game_pid` left by the exited parent (stop-external may signal a dead/reused pid).
- Non-systemd Linux or Windows escape.

## Log

## Fix attempt 1
Failure: manual test on Steam gamescope session: Steam stop leaves the old save/state; next launch pulls it. launch.log shows pushes completing, so the push child is not the problem.
Cause: `_sigterm_handler` calls `child.kill()` (SIGKILL), so RetroArch never writes its SRAM/autosave state on exit; the push uploads unchanged data. `game:stop-external` also SIGKILLs the emulator.
- [x] F1.1 `_sigterm_handler`: `child.terminate()` then a daemon `threading.Timer` (10s) that `kill()`s if still alive.
  - Files: src/cli/run.py
  - Reuses: existing handler, `threading` (already imported)
  - New: `_STOP_GRACE_SECONDS` constant - the grace window
- [x] F1.2 `game:stop-external`: SIGTERM (not SIGKILL) to the emulator pid; the handler's timer is the hard-kill fallback.
  - Files: src/gui/electron/game.ts
  - Reuses: existing handler
  - New: none
- [x] F1.3 Tests: real child that traps SIGTERM and writes a marker (graceful exit gets the marker); real child that ignores SIGTERM is killed after the grace window.
  - Files: src/tests/test_run_sigterm.py
  - Reuses: real-subprocess pattern from test_run_detach.py
  - New: new file - none exists for the handler
- [x] F1.4 Docs: GOTCHAS.md + CLAUDE.md note (SIGTERM first, SIGKILL after grace; #742).
  - Files: src/docs/GOTCHAS.md, CLAUDE.md

## Fix attempt 2
Failure: manual test, Steam "Exit game": `.srm` and `.state.auto` not rewritten (last written 16:19:32, later sessions logged "Pushed state" only), so the push uploads an unchanged save.
Cause: RetroArch's SIGTERM handler starts a clean shutdown on the first signal and calls `_exit(1)` on the second (frontend/drivers/platform_unix.c), skipping SRAM/autosave writes. Steam's reaper SIGTERMs the whole tree (RetroArch and `emusync run`), and `_sigterm_handler` immediately forwards a second SIGTERM. `game:stop-external` does the same (signals both pids).
- [x] F2.1 `_sigterm_handler`: don't signal the child immediately. A daemon timer after `_FORWARD_DELAY_SECONDS` (3s) sends SIGTERM only if the child is still alive; the existing `_STOP_GRACE_SECONDS` timer still SIGKILLs. Repeat SIGTERMs to emusync must not start more timers (guard with a module flag reset in `_launch_and_wait`... or simply check `child.poll()` and a `_stopping` flag).
  - Files: src/cli/run.py
  - Reuses: existing handler, threading.Timer
  - New: `_FORWARD_DELAY_SECONDS` constant
- [x] F2.2 `game:stop-external`: signal only the emusync pid (the CLI forwards one SIGTERM to the emulator); drop the direct emulator SIGTERM.
  - Files: src/gui/electron/game.ts
- [x] F2.3 Tests: child that, like RetroArch, exits cleanly on the first SIGTERM and writes "dirty" on a second: signaling both child and parent ends with a clean marker; child that ignores SIGTERM still gets forwarded SIGTERM then SIGKILL.
  - Files: src/tests/test_run_sigterm.py
- [x] F2.4 Docs: GOTCHAS.md + CLAUDE.md: never double-SIGTERM RetroArch (second signal = `_exit` with no save).
  - Files: src/docs/GOTCHAS.md, CLAUDE.md
