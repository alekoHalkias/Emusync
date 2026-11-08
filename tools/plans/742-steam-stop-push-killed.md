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
