# Plan: #616 Add game-location refresh tool with broken-ROM detection and auto-re-link

Issue: #616
Branch: feature/616-game-location-refresh
PR: none
Status: implementing
Fix attempts: 0

## Goal
Add a "Refresh locations" button that flags games with missing ROMs via a red exclamation badge, a modal to re-link broken ROMs at launch time, and a background scan that auto-fixes other broken references.

## Design Alignment
- **Visual Pattern**: New `game-card-badge-broken` badge follows existing badge pattern (16x16 icon, top-right corner overlay, `game-card-badges` container). Red `#e5484d` background with white `!` icon.
- **Recommendations**: Add `files:exists` IPC for batch path checks (simplest approach, no existing IPC does file-existence-only). Reuse `emulator:scan` IPC for background scan. Reuse `config:addRecentFolder` IPC for persisting library paths.

## Steps
- [ ] 1. Add `files:exists` IPC handler in `electron/files.ts` — simple `existsSync` wrapper returning boolean.
  - Files: src/gui/electron/files.ts
  - Reuses: `existsSync` from `fs` (already imported)
  - New: `files:exists` IPC — no existing IPC does bare file-existence check; `files:get-latest-in-folder` returns metadata not a boolean

- [ ] 2. Add `isBrokenLocation` field to `GameRow` type in `game-list/types.ts`.
  - Files: src/gui/renderer/src/components/game-list/types.ts
  - Reuses: existing GameRow type augmentation pattern (isLocal, offline, etc.)
  - New: one field — `isBrokenLocation?: boolean`

- [ ] 3. Update `emusync.d.ts` to declare `emusync.files.exists(path: string): Promise<boolean>`.
  - Files: src/gui/renderer/src/emusync.d.ts
  - Reuses: existing IPC type declarations pattern
  - New: one method declaration

- [ ] 4. Add red exclamation badge to GameCard.tsx — new `game-card-badge-broken` overlay, shown when `game.isBrokenLocation` is true. Icon: inline SVG exclamation circle, red `#e5484d` background.
  - Files: src/gui/renderer/src/components/GameCard.tsx
  - Reuses: existing `game-card-badges` container (line 82), same badge structure as `game-card-badge-locked` (line 88-92)
  - New: one badge conditional + one SVG icon — follows exact same pattern as existing badges

- [ ] 5. Add CSS for the new badge in `src/gui/renderer/src/styles.css` — `.game-card-badge-broken` with red background, white text.
  - Files: src/gui/renderer/src/styles.css
  - Reuses: existing `.game-card-badge` base styles
  - New: one CSS rule — color variation only

- [ ] 6. Add "Refresh locations" button to GameGrid.tsx header — after the gear button, before "Select All". On click, iterates local games, calls `files:exists` for each rom_path, sets `isBrokenLocation` on broken ones, shows toast summary.
  - Files: src/gui/renderer/src/components/GameGrid.tsx
  - Reuses: existing header button pattern (`btn btn-ghost game-grid-header-btn`), toast pattern (bulkMsg div)
  - New: refresh state + handler function — follows existing bulk action patterns (bulk download, bulk add to Steam)

- [ ] 7. Create LocationResolverModal.tsx — modal prompting user to locate a ROM file/folder when the stored path is missing. Uses `dialog:openFile` for single-file ROMs (pre-filtered by console ROM extensions), `dialog:openFolder` for Switch-style games. On selection, calls `api.ts` PUT /games/{slug}/device to update rom_path, derives save_path/state_path using import-wizard heuristics, persists folder via `config:addRecentFolder`, then signals GameGrid to launch.
  - Files: src/gui/renderer/src/components/LocationResolverModal.tsx (new)
  - Reuses: Modal.tsx wrapper, dialog IPC from files.ts, config:addRecentFolder from config-store.ts, api.ts PUT endpoint
  - New: entire component — new UX flow for re-linking. Save/state derivation reuses logic from scan.ts:matchSaveFile pattern (basename matching, content-dir subfolder, core-subfolder fallback)

- [ ] 8. Integrate LocationResolverModal into GameGrid.tsx — guard the `onPlay` handler: if the game's rom_path is broken, open the modal instead of launching. Wire close/re-link callback to refresh the game list and re-attempt launch.
  - Files: src/gui/renderer/src/components/GameGrid.tsx
  - Reuses: existing modal pattern (netPlayTarget state, NetworkPlaySetup render)
  - New: broken-rom state + handler — follows same lifted-state pattern as NetworkPlaySetup

- [ ] 9. Add background scan after re-link — on successful rom_path update, call `emulator:scan` IPC on the found folder + its parent siblings for the same console. Match scan results against existing broken games on this device; for any ROM that matches a broken game's slug, auto-update rom_path via the API. Show toast summary.
  - Files: src/gui/renderer/src/components/GameGrid.tsx
  - Reuses: emulator:scan IPC (emulator/ipc.ts:32), existing toast pattern, api.ts PUT endpoint
  - New: scan-matching logic — iterate scan results, match by basename against broken games, bulk update via existing API

- [ ] 10. Tests: Add integration tests in `src/tests/test_game_location_refresh.py` (or extend existing test file).
  - Test cases:
    - Refresh detects missing rom_path
    - Refresh ignores existing rom_path
    - Re-link updates rom_path via API
    - Background scan matches broken games by basename
    - Save/state path derivation uses same heuristics as import wizard
  - Files: src/tests/test_game_location_refresh.py (new)
  - Reuses: `client` fixture, `Store` pattern, `tmpdir` isolation
  - New: test file — backend integration tests for API-level behavior (PUT /games/{slug}/device with new rom_path)

- [ ] 11. Docs: Update CLAUDE.md GUI section with new badge and refresh button behavior. Update ARCHITECTURE.md IPC section with `files:exists`.
  - Files: src/docs/ARCHITECTURE.md, src/docs/GOTCHAS.md (if applicable)
  - Reuses: existing documentation patterns
  - New: documentation entries for new IPC and UI features

## Testing
- **Test File**: `src/tests/test_game_location_refresh.py`
- **Test Cases**:
  - `test_refresh_detects_missing_rom`: Register a game with a rom_path pointing to a non-existent file; verify `game_devices.rom_path` is unchanged but the game is flagged as broken.
  - `test_refresh_ignores_existing_rom`: Register a game with a real rom_path; verify it is NOT flagged as broken.
  - `test_relink_updates_rom_path`: PUT /games/{slug}/device with a new rom_path; verify the store reflects the update and the game is now valid.
  - `test_relink_updates_rom_path_with_network`: PUT with `rom_source='network'` + new paths; verify both `rom_path` and `rom_source` are updated.
  - `test_save_state_derivation`: Given a new rom_path, verify save_path derivation matches import-wizard heuristics (basename matching, content-dir subfolder, core-subfolder fallback).
- **Edge Cases**:
  - `test_broken_rom_on_other_device`: A game where `isLocal=false` — refresh should NOT flag it as broken (broken-rom checks only apply to local games).
  - `test_relink_switch_folder_rom`: A Switch game where the ROM is a folder (e.g. `GAME/`); verify the folder-based rom_path is accepted.
  - `test_relink_preserves_other_fields`: PUT updates rom_path but preserves launch_command, save_path, state_path, rom_folder_path.
- **Integration Points**:
  - `PUT /games/{slug}/device` endpoint (src/server/api/games.py:154) — verify rom_path update persists in real SQLite.
  - Store `set_game_device` method — verify round-trip through SQLite.

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): yes (files:exists). New CLI subcommand: no. Config/data file change: no.

## Not in this plan
- Network ROM validation (only local rom_path checked)
- Server-side broken-rom detection (client-only for v1)
- Bulk re-link of multiple broken games at once

## Log
- 2025-10-29 fplan: 11 steps written, visual_pattern=red exclamation badge on game card
