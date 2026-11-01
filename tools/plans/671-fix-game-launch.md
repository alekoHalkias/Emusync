# Plan: #671 Fix games not launching from EmuSync

Issue: #671
Branch: feature/671-fix-game-launch
PR: none
Status: planned
Fix attempts: 0

## Goal
Find why `emusync run <slug>` no longer starts the emulator and fix it at the source, with a regression test.

## Design Alignment
- **Backend Pattern**: launch flows through `cli/run.py:_resolve_launch_command` then `shlex.split` then `_launch_and_wait`; fix stays in that path, no new modules.
- **Recommendations**: none. Root cause is not yet known; step 1 reproduces it before any code change.

## Steps
- [x] 0. Finding (user: CLI works, GUI and Steam do not): `src/emusync` (Steam launcher, `launcher:path`) execs `$SCRIPT_DIR/.venv/bin/python`, i.e. `src/.venv`, which does not exist since the #611 layout move (venvs live at `.venv` and `.cache/.venv`). Running `src/emusync run --help` fails with "No such file". Steam cause confirmed. GUI cause not yet confirmed: `runtime.ts` PYTHON resolves `.cache/.venv` fine in a dev checkout; check how the GUI is run (AppImage/EMUSYNC_* env) and capture spawn stderr.
- [x] 1. Reproduce the GUI case: run `.venv/bin/python src/emusync.py run <slug>` in a terminal on an affected device (the GUI spawns it with `stdio: "ignore"`, which hides the error) and record the stderr/exit code in the handoff Log. Candidates: `_resolve_launch_command` returning None, empty `launch_command`, `%ROM%` resolution, network/share changes from #663, device dedupe from #657 (device_id/game_devices lookup).
  - Files: none (investigation only)
  - Reuses: existing CLI
  - New: none
- [x] 2. Fix the identified cause at its origin in the shared function.
  - Files: determined by step 1 (Steam: src/emusync wrapper venv path; GUI: TBD from step 1)
  - Reuses: `_resolve_launch_command`, `resolve_rom_path`
  - New: none expected
- [x] 3. Tests (extend test_run_reconcile.py, reuse its existing fixtures): regression test for the identified failure in src/tests/test_integration.py (or the module matching the cause). No mocks, real SQLite.
- [x] 4. Docs: none needed unless the cause reveals a rule worth adding to src/docs/GOTCHAS.md.

## Testing
- **Test File**: src/tests/test_run_reconcile.py (existing run/launch tests, real SQLite)
- **Test Cases**:
  - regression: the reproduced failing launch scenario launches the emulator command (shape fixed after step 1)
- **Edge Cases**:
  - network ROM with live master vs localized copy; `%ROM%` token and legacy baked-in path
- **Integration Points**:
  - `_resolve_launch_command` -> `shlex.split` -> `_launch_and_wait`

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
Surfacing launch errors in the GUI (game.ts uses stdio ignore); file separately if wanted.

## Log
Step 1: reproduced by inspection; GUI stdio hidden, Steam wrapper venv path missing.
Step 2: fixed src/emusync venv lookup; GUI launch now writes <data_dir>/launch.log (GUI root cause still unconfirmed).
Note: pre-existing tsc errors (files.ts rt.PYTHON, steam-shortcut-editor types) are out of scope.

## Fix attempt 1
Cause: launch.log showed `can't open file src/gui/out/emusync.py`: runtime.ts SCRIPT used `../emusync.py` after #611; from out/main it must be `../../../emusync.py`. Also fixes launcher:path (Steam) and PYTHON venv lookup.
- [x] F1.1 runtime.ts SCRIPT path restored. The %ROM% display in the editor is by design (#518), not the cause.
