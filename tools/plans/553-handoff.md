# Handoff: #553 Scan directory-style PS3 games (PS3_GAME/) for RPCS3

## Metadata
- Issue: #553
- Branch: feature/553-ps3-dir-roms
- PR: none
- Status: planned
- Created: 2026-10-28
- Fix attempts: 0

## 1. Issue
### Summary
Support ROM scanning for PS3 games stored as an extracted folder (`<Game>/PS3_GAME/` with `USRDIR/EBOOT.BIN`) rather than a single `.iso`/`.pkg` file.

### Motivation
Split out of #422 / PR #526, which only scans `.iso` and `.pkg`. Many RPCS3 libraries are extracted folders, and no scanner currently treats a directory as a ROM — `cli/detect.py`'s `_scan_rom_dir`, `cli/console.py`'s scan, and `gui/electron/emulator/scan.ts` all match files by extension only.

### Proposed Behavior / Steps to Reproduce
1. User has a PS3 game stored as `~/Emulation/roms/PS3/Game Name/PS3_GAME/USRDIR/EBOOT.BIN`
2. The import wizard should detect this directory as a ROM entry
3. The game should be importable with the directory path as `rom_path`
4. `emusync run` / push/pull should handle the directory (likely as a tar, similar to Switch)

### Affected Area
- `src/cli/detect.py` — `_scan_rom_dir()` (Python scanner, extension-only file match)
- `src/cli/console.py` — `_import_game()` wizard (uses `_scan_rom_dir`)
- `src/gui/electron/emulator/scan.ts` — `scanRomDir()` (TypeScript scanner, extension-only file match)
- `src/cli/consoles_data.py` — PS3 console definition (needs `rom_extensions` update)
- `src/gui/electron/emulator/types.ts` — `RomEntry.romPath` type (may need to accommodate directories)

### Acceptance Criteria
- [ ] Directory-style PS3 games (`PS3_GAME/` folders) are detected by both Python and TypeScript scanners
- [ ] The detected entry shows the game folder name (not `EBOOT.BIN`) as the display name
- [ ] File-style PS3 games (`.iso`, `.pkg`) continue to scan normally
- [ ] No regressions for other consoles

## 2. Design
### Scope: Backend-only. Scanner enhancement for PS3 directory-style ROMs. No UI changes needed — the import wizard receives entries from the scanner; directory entries appear like file entries with the folder name as display name.
### Backend Changes:
- `src/cli/detect.py` — `_scan_rom_dir()`: when scanning a directory, check if it contains `PS3_GAME/USRDIR/EBOOT.BIN`. If so, treat the parent directory as a ROM entry (yield the directory path, not the file). Display name = parent directory name.
- `src/gui/electron/emulator/scan.ts` — `scanRomDir()`: mirror the same logic — check for `PS3_GAME/USRDIR/EBOOT.BIN` inside subdirectories, yield the parent directory as a ROM entry.
- `src/cli/consoles_data.py` — PS3 console def: add `"rom_extensions": ["iso", "pkg", "chd", "dir"]` (or equivalent) so the scanner knows to look for directory ROMs on PS3.
- `src/gui/electron/emulator/types.ts` — `RomEntry.romPath` already accepts `string`; directories are valid paths, no type change needed.
### UI Changes: None.
### Plan Target: bplan (backend-only: scanner logic in Python + TypeScript, console def update)
### Sub-issues: none
### Difficulty: 4/10
### Backwards Compatibility: No breaking changes. Purely additive scanner behavior. File-style PS3 ROMs continue to work as before.

## 3. Frontend Plan
### Design Alignment: TBD
### Visual Pattern: TBD
### Recommendations: TBD

## 4. Backend Plan
### Design Alignment: Matches design — backend-only scanner enhancement. No UI, schema, IPC, or TOML changes. Directory entries appear as normal RomEntry with parent folder name as display name.
### Backend Pattern: Add `dir_rom_pattern` field to PS3 console def in `consoles_data.py`. Modify `_scan_rom_dir()` / `scanRomDir()` to accept `console_key`, check pattern before recursing into subdirectories. Yield matching directory as ROM entry, skip recursion. Wire console_key through call chain in `console.py` and GUI scan entry point.
### Recommendations: Plan at `tools/plans/553-ps3-dir-roms.md`. 5 steps, no breaking changes, no schema bump. Difficulty remains 4/10.

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: TBD
### Test Cases: TBD
### Edge Cases: TBD
### Integration Points: TBD

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps: See `tools/plans/553-ps3-dir-roms.md` — 5 steps: (1) add dir_rom_pattern to PS3 console def, (2) update Python scanner, (3) update TypeScript scanner, (4) wire console_key through call chain, (5) update PS3 comment.

## 9. Review
### Findings: TBD
### Blocked: TBD
### Blockers: TBD

## 10. Ship
### Status: pending
### PR: none
### Server Sync: pending
### Doc Sync: pending

## 11. Fix Attempts
### Attempt 1: none
### Attempt 2: none
### Attempt 3: none

## 12. Log
- 2026-10-28 issue: workflow initialized
- 2026-10-28 design: scope=backend (scanner + console def), plan_target=bplan, difficulty=4/10, breaking=no
- 2026-10-28 bplan: written to 553-ps3-dir-roms.md, 5 steps, no schema/IPC/config changes
