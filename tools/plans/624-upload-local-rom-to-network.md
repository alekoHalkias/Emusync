# Plan: #624 Add per-game upload of a local ROM to the network drive

Issue: #624
Branch: feature/624-upload-local-rom-to-network
PR: none
Status: implementing
Fix attempts: 0

## Goal
A local-source ROM can be uploaded to the console's network folder from game settings, turning the game into network-sourced with this device's copy kept as the local copy.

## Design Alignment
- **Visual Pattern**: second `btn` in the existing MoveLocalRomPanel row; same busy/message text.
- **Recommendations**: none.

## Steps
- [ ] 1. MoveLocalRomPanel: also load the console's `device_network_folder`; render the panel when the ROM is outside the local folder OR a network folder exists (local-source only); add "Add to network drive" button. Handler: rel = relPathUnder(romPath, [folder]), master = `${net}/${rel}`, `rom.uploadMaster(romPath, master)`, then `getGameDevice` + `setGameDevice` with rom_source network, rom_path master, local_rom_path = old romPath, rom_rel_path rel, rom_sha256, launch_command with old path replaced by master. Then notify parent.
  - Files: src/gui/renderer/src/components/game-config/MoveLocalRomPanel.tsx
  - Reuses: rom.uploadMaster (never overwrites), console-import/helpers.ts:relPathUnder, api.ts:getGameDevice/setGameDevice, resolveRomPaths.ts presence="local" logic
  - New: one handler - the import-wizard logic is embedded in a bulk loop and not callable per game.
- [ ] 2. GameConfig: on upload success set romSource to network, romPath to master, localRomPath to the local copy, launch command (new `onUploaded` prop), so the form matches server state and NetworkRomPanel appears.
  - Files: src/gui/renderer/src/components/GameConfig.tsx
  - Reuses: existing setRomSource/setRomPath/setLocalRomPath/setLaunchCommand
- [ ] 3. Tests: none - no Python/API change, renderer/Electron have no harness; manual check. `make test-changed` and tsc must not regress.
- [ ] 4. Docs: ARCHITECTURE.md MoveLocalRomPanel line mentions upload.

## Testing
- **Test File**: none (manual + tsc + make test-changed)
- **Test Cases**: local ROM with network folder shows button; after upload game shows as network with local copy.
- **Edge Cases**: master already exists (skipped, treated as authoritative); no network folder (no button); network share unmounted (error shown, state unchanged).
- **Integration Points**: PUT /games/{slug}/device persists network fields.

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
Moving the ROM and uploading in one click; deleting the local copy after upload.

## Log
