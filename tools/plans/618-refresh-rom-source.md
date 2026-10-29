# Plan: #618 Refresh locations: correct ROM source (local/network) from folder

Issue: #618
Branch: feature/618-refresh-rom-source
PR: none
Status: implemented
Fix attempts: 0

## Goal
Make Refresh locations also set each game's rom_source to 'local' or 'network' according to which of the console's configured folders contains its ROM.

## Design Alignment
- **Visual Pattern**: no new UI; reuses the existing bulkMsg toast from #616.
- **Recommendations**: none. Folder semantics: local = device_local_folder or device_game_folder, network = device_network_folder. Longest matching prefix wins; no match leaves the game unchanged. Switching to network sets rom_rel_path to the path relative to the network folder and keeps local_rom_path; switching to local only flips rom_source (rom_path is already the local file).

## Steps
- [x] 1. Add a pure helper `sourceFor(romPath, folders)` returning 'local' | 'network' | null (longest-prefix match, slash-normalised, case-sensitive) and `relTo(folder, path)`.
  - Files: src/gui/renderer/src/components/game-list/useBrokenRoms.ts
  - Reuses: existing `norm` helper in that file
  - New: two small functions - no existing path-containment helper in the renderer
- [x] 2. Extend `refresh(deviceId)` to also fetch `getDeviceConsoles`, and for each present local-or-network game whose console row matches (`console_name` equals `game.console`, case-insensitive) and whose detected source differs from `romSource`, GET + PUT the device config with the new `rom_source` (and `rom_rel_path` when switching to network). Return `{ missing, corrected }`. Per-game failures are skipped.
  - Files: src/gui/renderer/src/components/game-list/useBrokenRoms.ts
  - Reuses: `updateRom`-style GET/PUT in the same file (generalise to take a patch), `getDeviceConsoles` in api.ts
  - New: none beyond the loop
- [x] 3. Update GameGrid `handleRefreshLocations` to pass `currentDeviceId` (from `useDevices`) and extend the toast: missing count and corrected count; call `onChanged()` when anything was corrected.
  - Files: src/gui/renderer/src/components/GameGrid.tsx
  - Reuses: `useDevices` (as in ConsoleFoldersModal), existing bulkMsg toast
  - New: none
- [x] 4. Tests: extend src/tests/test_game_location_refresh.py with the GET+PUT source flips (local to network sets rom_rel_path and keeps local_rom_path; network to local keeps rom_path).
  - Files: src/tests/test_game_location_refresh.py
  - Reuses: `_relink`-style helper, `client` fixture
  - New: 2 test cases (the prefix matching itself is renderer-only; repo has no renderer harness)
- [x] 5. Docs: one sentence in CLAUDE.md GUI rule for Refresh locations.
  - Files: CLAUDE.md

## Testing
- **Test File**: src/tests/test_game_location_refresh.py
- **Test Cases**:
  - test_source_flip_to_network: PUT with rom_source=network and rom_rel_path; local_rom_path and rom_path preserved.
  - test_source_flip_to_local: PUT with rom_source=local; rom_path preserved.
- **Edge Cases**:
  - Prefix matching (longest wins, no match unchanged) is renderer-only; no renderer harness exists, covered by manual check.
- **Integration Points**: PUT /games/{slug}/device on real SQLite.

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
- Moving or copying ROM files; only the stored source label changes.
- Re-deriving rom_path from the folder.

## Log
Steps 1-5 committed together; step 1 also exports sourceFor returning {source, folder} (folder needed for rel path).
