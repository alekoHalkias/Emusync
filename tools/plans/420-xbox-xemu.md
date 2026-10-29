# Plan: #420 Add original Xbox support via Xemu standalone

Issue: #420
Branch: feature/420-xbox-xemu
PR: none
Status: planned
Fix attempts: 0

## Goal
Add the original Xbox console entry with Xemu standalone emulator support, treating the virtual HDD image as a shared console memcard.

## Design Alignment
- **Backend Pattern**: Follow the PS2/PCSX2 standalone pattern — `_XEMU` dict in `consoles_data.py`, `xbox` entry in `_IMPORT_CONSOLES` with `shared_memcard=True`, HDD image resolved in `_resolve_shared_memcard_save_state()`.
- **Recommendations**: The Xbox HDD image is a single `.qcow2` file in the Xemu data directory. Resolution probes for any `.qcow2` file first, falls back to the canonical `xbox_hdd.qcow2` path.

## Steps
- [ ] 1. Add `_XEMU` standalone definition and `xbox` console entry to `consoles_data.py`
  - Files: `src/cli/consoles_data.py`
  - Reuses: `_PCSX2` as shape template; `_ROM_EXTENSIONS` pattern
  - New: `_XEMU` dict — native_bins: `/usr/bin/xemu`, `~/.local/bin/xemu`, `~/Applications/Xemu.AppImage`; flatpak_id: `com.xemu_emu.xemu`; dirs: native save=`~/.xemu/` (states), memcard=`~/.xemu/xbox_hdd.qcow2`; flatpak save=`~/.var/app/com.xemu_emu.xemu/data/xemu/`, memcard=`~/.var/app/com.xemu_emu.xemu/data/xemu/xbox_hdd.qcow2`; console entry: key=`xbox`, label=`Xbox`, abbr=`Xbox`, rom_extensions=`["iso", "xiso"]`, databases=`["Sony - PlayStation"]` (no, Xbox has its own database — actually Xbox has no libretro core so databases field is unused for core matching, but the seed still populates the field. Looking at PS2: it has `"databases": ["Sony - PlayStation 2"]` even though it has no system_keys. For Xbox, there's no libretro database since there's no libretro core. The databases field can be empty `[]` — it only matters if a libretro core's .info matches it.)
  - Actually, looking at the PS2 entry: it has `"databases": ["Sony - PlayStation 2"]` even though standalone-only. But PS2's databases entry is used to match RetroArch cores (if any existed). For Xbox, there are no libretro cores, so databases should be `[]`.

- [ ] 2. Add `xiso` to `_ROM_EXTENSIONS` set
  - Files: `src/cli/consoles_data.py`
  - Reuses: existing set pattern
  - New: `"xiso"` entry

- [ ] 3. Add Xbox HDD image resolution to `_resolve_shared_memcard_save_state()` in `detect.py`
  - Files: `src/cli/detect.py`
  - Reuses: `glob.glob()` pattern from 3DS resolution; `_find_first_by_ext()` helper
  - New: `elif console_abbr == "Xbox"` branch — probe for `.qcow2` files in save_dir (Xemu data dir), fall back to canonical `xbox_hdd.qcow2` path

- [ ] 4. Add Xbox tests to `test_new_consoles.py`
  - Files: `src/tests/test_new_consoles.py`
  - Reuses: `test_ps2_card_resolution_unchanged` pattern, `test_3ds_standalone_azahar_def_follows_pcsx2_pattern` pattern
  - New: `test_xbox_console_def_follows_ps2_pattern()`, `test_xbox_shared_membership()`, `test_xbox_standalone_xemu_def()`, `test_xbox_card_prefers_existing_qcow2()`, `test_xbox_card_falls_back_to_default()`

- [ ] 5. Tests: `make test-changed`
  - Run the full test suite or changed-file subset to verify no regressions.

## Checklist
Schema bump: no. New IPC channel: no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
- GUI/console icon (art.ts) — trivial addition, done as part of step 1 or as a follow-up
- TypeScript scan.ts mirror — trivial mirror of Python logic, done alongside step 3

## Log
- 2025-07-27 bplan: 5 steps written, backend_pattern=PS2-standalone-shared-memcard
