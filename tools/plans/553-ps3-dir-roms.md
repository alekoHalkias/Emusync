# Backend Plan: #553 Scan directory-style PS3 games (PS3_GAME/) for RPCS3

## Goal

Extend the ROM scanner to detect PS3 games stored as extracted folders (`<Game>/PS3_GAME/USRDIR/EBOOT.BIN`) alongside existing `.iso`/`.pkg` file detection.

## Design Alignment

Matches the design posted to issue #553: backend-only scanner enhancement. No UI changes, no schema bump, no new IPC channels. Directory entries appear as normal `RomEntry` objects with the parent folder name as display name.

## Steps

### Step 1: Add `dir_rom_pattern` to PS3 console definition

**File:** `src/cli/consoles_data.py`

Add `"dir_rom_pattern": "PS3_GAME/USRDIR/EBOOT.BIN"` to the PS3 console entry in `_IMPORT_CONSOLES` (line ~237). This pattern tells the scanner that a directory containing this path structure should be treated as a ROM entry.

### Step 2: Update Python scanner `_scan_rom_dir()`

**File:** `src/cli/detect.py`

Modify `_scan_rom_dir(directory, depth=0)` to accept an optional `console_key` parameter. Before recursing into a subdirectory, check if the subdirectory contains the console's `dir_rom_pattern`. If it matches, yield the subdirectory path as a ROM entry and skip recursing into it. If not, recurse normally.

Pattern matching logic:
- Split pattern on `/` to get path components
- Walk from the scan directory, following each component
- If all components exist (directories except the last, which is a file), the pattern matches

### Step 3: Update TypeScript scanner `scanRomDir()`

**File:** `src/gui/electron/emulator/scan.ts`

Mirror the Python logic. Add `consoleKey` parameter to `scanRomDir()`. Before recursing into a subdirectory, check for the console's `dir_rom_pattern` (looked up from a console definitions map or passed as a parameter). If matched, yield the subdirectory path and skip recursion.

### Step 4: Wire `console_key` through the call chain

**Files:** `src/cli/console.py`, `src/gui/electron/emulator/main.ts` (or wherever `scanRomDir` is called)

Pass the console key from the import wizard through to `_scan_rom_dir()` / `scanRomDir()`. The console key is already available at the call site (the user selects a console before scanning).

### Step 5: Update PS3 comment in consoles_data.py

**File:** `src/cli/consoles_data.py`

Update the PS3 console comment (line 234-236) to reflect that directory-style games are now supported.

### Step 6: Tests — add `test_ps3_dir_roms.py`

**File:** `src/tests/test_ps3_dir_roms.py`

New test file (follows `tmp_path` unit test pattern from `test_cli_console_import.py`). Cases:
- Directory ROM pattern matches `PS3_GAME/USRDIR/EBOOT.BIN` — returns parent directory path
- Directory ROM pattern does not match incomplete structure — falls through to normal recursion
- Directory ROM pattern not present — normal recursion unchanged
- File-style `.iso`/`.pkg` still detected alongside directory ROMs
- Depth limit (3) still applies to directory ROM detection
- Non-PS3 consoles are unaffected (pattern only checked when `console_key="ps3"`)

Reuses: `tmp_path` fixture from pytest, `monkeypatch` for environment isolation. No existing test covers `_scan_rom_dir()` so this is a new file (justification: scanner logic has zero existing test coverage).

## Checklist

- [x] Schema bump: no
- [x] New IPC channel: no
- [x] New DB tables: no
- [x] Breaking changes: no
- [x] TOML config changes: no
- [x] `emusync.d.ts` update: no
- [x] Server restart needed: no (scanner is client-side)

## Testing
- **Test File**: `src/tests/test_ps3_dir_roms.py`
- **Test Cases**:
  - `test_scan_rom_dir_detects_ps3_dir_rom`: PS3_GAME/USRDIR/EBOOT.BIN pattern yields parent directory
  - `test_scan_rom_dir_incomplete_pattern_falls_through`: missing USRDIR/EBOOT.BIN recurses normally
  - `test_scan_rom_dir_non_ps3_unaffected`: non-PS3 console_key skips dir_rom check
  - `test_scan_rom_dir_file_and_dir_together`: .iso and PS3_GAME/ entry both found
  - `test_scan_rom_dir_depth_limit_on_dir_rom`: depth > 3 returns empty for dir ROM
- **Edge Cases**:
  - Nested PS3_GAME inside another PS3_GAME (should not double-match)
  - EBOOT.BIN is a directory (is_file() check prevents false match)
  - Permission error on PS3_GAME subdirectory
- **Integration Points**: None — scanner is pure client-side logic, no server/DB involvement.

## Not in this plan
- RPCS3 launch command for directory ROMs (EBOOT.BIN path resolution at run time)
- ROM push/pull for directory ROMs (reuses Switch folder tar path, #441)
- TypeScript scanner tests (GUI tests are out of scope for this backend plan)

## Log

- None identified. Purely additive scanner behavior. File-style PS3 ROMs continue to work as before.
- The `dir_rom_pattern` check is console-specific, so it won't affect other consoles.
- Depth limit (3) still applies to directory ROM detection.
