# Handoff: #420 Add original Xbox support via Xemu standalone

## Metadata
- Issue: #420
- Branch: feature/420-xbox-xemu
- PR: none
- Status: implementing
- Created: 2025-07-27
- Fix attempts: 0

## 1. Issue
### Summary
Add the original Xbox as a detectable console, using Xemu as its standalone emulator, following the PCSX2/Dolphin standalone pattern.

### Motivation
Part of the console-expansion survey in #417 (Tier 2: standalone-only, no libretro core).

### Proposed Behavior / Steps to Reproduce
- New `xbox` console entry in `consoles_data.py` with Xemu as the standalone emulator
- Xemu save data lives inside a virtual hard drive image (`xbox_hdd.qcow2`) rather than a plain folder — confirm whether per-game sync is even feasible without mounting the image, or whether this needs a shared-console-card approach (whole HDD image synced like a PS2 memcard) instead of per-game saves
- ROM extensions: `iso`, `xiso`

### Affected Area
- `src/cli/consoles_data.py` — new console def + standalone definition
- `src/cli/detect.py` — emulator detection for Xemu
- `src/cli/console.py` — save/state resolution for Xbox
- `src/cli/run.py` — shared memcard state sets
- `src/gui/electron/emulator/scan.ts` — TypeScript mirror of save resolution
- `src/gui/electron/emulator/types.ts` — ROM_EXTENSIONS
- `src/gui/electron/art.ts` — console icon/logo
- `src/tests/test_new_consoles.py` — detection tests

### Acceptance Criteria
- Standalone def added to `cli/consoles_data.py`, registered on a new `xbox` console entry
- Save/state resolution strategy confirmed against Xemu's actual on-disk layout before writing detection code
- Detection tests mirroring `tests/test_new_consoles.py` patterns

## 2. Design
### Scope: Add Xbox console entry with Xemu standalone support. Pure additive change — no schema/API changes needed.
### Backend Changes:
  - `consoles_data.py`: Add `_XEMU` standalone dict (native_bins, flatpak_id, dirs for HDD image + states), add `xbox` console entry to `_IMPORT_CONSOLES` (shared_memcard=True, rom_extensions=["iso","xisi"]), add "xiso" to `_ROM_EXTENSIONS`
  - `detect.py`: Add Xbox case to `_resolve_shared_memcard_save_state()` — resolve HDD image path (~/.xemu/xbox_hdd.qcow2 or Flatpak equivalent), using first existing .qcow2 file in the Xemu data dir
### UI Changes:
  - `types.ts`: Add "xiso" to `ROM_EXTENSIONS`
  - `scan.ts`: Add Xbox case to `resolveSharedCard()` — mirror Python HDD image resolution
  - `art.ts`: Add "xbox" to `CARBON_FOLDER` for console wheel icon
### Plan Target: bplan
### Sub-issues: none
### Difficulty: 3/10
### Backwards Compatibility: No breaking changes. All shared-memcard infrastructure (API endpoints, store methods, sync client, GUI memcard handler) already exists.

## 3. Frontend Plan
### Design Alignment: N/A (bplan only; TS changes are trivial mirrors of Python logic)
### Visual Pattern: N/A
### Recommendations: N/A

## 4. Backend Plan
### Design Alignment: Follow PS2/PCSX2 standalone pattern — `_XEMU` dict, `xbox` console entry with `shared_memcard=True`, HDD image resolved in `_resolve_shared_memcard_save_state()`.
### Backend Pattern: Standalone emulator def + shared-memcard console. HDD image probed for `.qcow2` files in Xemu data dir, falls back to canonical `xbox_hdd.qcow2` path.
### Recommendations: None.

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: `src/tests/test_new_consoles.py`
### Test Cases:
  1. `test_xbox_console_def_follows_ps2_pattern()` — console def structure
  2. `test_xbox_shared_membership()` — shared memcard membership
  3. `test_xbox_standalone_xemu_def_follows_pcsx2_pattern()` — standalone def structure
  4. `test_xbox_card_prefers_existing_qcow2_over_default(tmp_path)` — HDD image resolution finds existing .qcow2
  5. `test_xbox_card_falls_back_to_default_when_no_qcow2_exists(tmp_path)` — fallback to canonical path
  6. `test_xbox_standalone_xemu_lists_native_and_flatpak_together(monkeypatch, tmp_path)` — both native+flatpak detected
### Edge Cases: Multiple .qcow2 files (first found wins); .qcow2 is a directory (should not match)
### Integration Points: `_resolve_shared_memcard_save_state()` (detect.py), `_SHARED_MEMCARD_CONSOLES` (run_ps2.py), `_detect_emulators_for_console()` (detect.py)

## 8. Implementation Steps
### Steps:
  1. Add `_XEMU` standalone definition and `xbox` console entry to `consoles_data.py`
     - Files: `src/cli/consoles_data.py`
     - Reuses: `_PCSX2` shape template, `_ROM_EXTENSIONS` pattern
  2. Add `xiso` to `_ROM_EXTENSIONS` set
     - Files: `src/cli/consoles_data.py`
     - Reuses: existing set pattern
  3. Add Xbox HDD image resolution to `_resolve_shared_memcard_save_state()` in `detect.py`
     - Files: `src/cli/detect.py`
     - Reuses: `glob.glob()` pattern from 3DS resolution, `_find_first_by_ext()` helper
  4. Add Xbox tests to `test_new_consoles.py` (6 test functions)
     - Files: `src/tests/test_new_consoles.py`
     - Reuses: `test_ps2_card_resolution_unchanged`, `test_3ds_*` patterns
  5. Run `make test-changed` to verify

## 9. Review
### Findings: TBD
### Blocked: TBD
### Blockers: TBD

## 10. Ship
### Status: done
### PR: https://github.com/alekoHalkias/Emusync/pull/615
### Server Sync: done (feature/420-xbox-xemu branch on server)
### Doc Sync: pending

## 11. Fix Attempts
### Attempt 1: none
### Attempt 2: none
### Attempt 3: none

## 12. Log
- 2025-07-27 issue: workflow initialized, branch feature/420-xbox-xemu created
- 2025-07-27 design: scope=backend+trivial-ts-mirror, plan_target=bplan, difficulty=3/10, breaking=no
- 2025-07-27 bplan: 5 steps written, backend_pattern=PS2-standalone-shared-memcard
- 2025-07-27 tplan: test_file=src/tests/test_new_consoles.py, 6 test cases defined
- 2025-07-27 implement: steps 1-6 done (consoles_data.py, detect.py, scan.ts, types.ts, art.ts, test_new_consoles.py)
