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

## Checklist

- [x] Schema bump: no
- [x] New IPC channel: no
- [x] New DB tables: no
- [x] Breaking changes: no
- [x] TOML config changes: no
- [x] `emusync.d.ts` update: no
- [x] Server restart needed: no (scanner is client-side)

## Risks

- None identified. Purely additive scanner behavior. File-style PS3 ROMs continue to work as before.
- The `dir_rom_pattern` check is console-specific, so it won't affect other consoles.
- Depth limit (3) still applies to directory ROM detection.
