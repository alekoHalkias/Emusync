# Plan: #702 Quote emulator path in launch commands and parse them Windows-safely

Issue: #702
Branch: feature/702-launch-command-quoting
PR: none
Status: planned
Fix attempts: 0

## Goal
Launch commands built with a spaced or backslashed emulator path, and previously stored unquoted ones, launch with the right argv.

## Design Alignment
- **Backend Pattern**: one shared pure helper in cli/common.py used by both launch sites (run.py, run_offline.py); no API/schema change.
- **Recommendations**: none

## Steps
- [ ] 1. Add `split_launch_command(cmd)` to cli/common.py: tokenize with `shlex.split(posix=False)` on Windows (quotes stripped) else POSIX; if argv[0] is not an existing file or on PATH, join the shortest run of leading tokens that is an existing file (handles stored unquoted `/opt/My Emu/emu` and `C:\Program Files\...`).
  - Files: src/cli/common.py
  - Reuses: stdlib shlex, shutil.which, os.path
  - New: helper - no existing splitter handles Windows or legacy unquoted exec paths
- [ ] 2. Use it in both launch sites, and quote the bare/single-quoted `%ROM%` substitution in `_resolve_launch_command` so a ROM path with spaces stays one argument.
  - Files: src/cli/run.py (line ~102, ~253), src/cli/run_offline.py (line ~150)
  - Reuses: existing `_resolve_launch_command`, `ROM_TOKEN`
  - New: none
- [ ] 3. Quote exec_path where commands are built.
  - Files: src/cli/console.py (364-366), src/gui/electron/emulator/scan.ts (303-304)
  - Reuses: existing f-strings; only add quotes
  - New: none
- [ ] 4. Tests: src/tests/test_launch_command_split.py - spaced exec path (quoted and legacy unquoted using a real temp file), Windows-style tokenization (call internal split with nt mode), bare `%ROM%` with spaces yields one arg, plain commands unchanged; extend test_launch_command_token.py for the bare-token case. No mocks, real files.
- [ ] 5. Docs: none needed - internal parsing fix, no CLI/IPC/config change; one line in src/docs/GOTCHAS.md only if review asks.

## Testing
- **Test File**: src/tests/test_launch_command_split.py (new, plain pytest, real temp files); extend src/tests/test_launch_command_token.py
- **Test Cases**:
  - quoted spaced exec path: argv[0] is the full path
  - legacy unquoted spaced exec path (real temp file): tokens re-joined into argv[0]
  - Windows tokenization (`nt` flag on helper): backslashes kept, quotes stripped
  - bare `%ROM%` with spaced ROM path: one argument; single-quoted token too
- **Edge Cases**:
  - plain command with exec on PATH is unchanged
  - nonexistent exec: returns the plain tokenization, no exception
- **Integration Points**: `_resolve_launch_command` output feeds `split_launch_command`; both run.py and run_offline.py call it

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
Migrating stored commands in the DB (parser tolerates them); single-quoted-path edge cases beyond `'%ROM%'`.
## Log
