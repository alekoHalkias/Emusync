# Plan: #622 Allow moving local ROMs outside the console default folder

Issue: #622
Branch: feature/622-move-local-rom
PR: none
Status: implementing
Fix attempts: 0

## Goal
A local-source ROM outside its console's default local folder can be moved into it from game settings, updating rom_path and the launch command.

## Design Alignment
- **Visual Pattern**: reuses the plain `btn` + inline message row used by NetworkRomPanel; no new pattern.
- **Recommendations**: none. Cancel/progress modal is skipped: a same-filesystem move is an instant rename; cross-filesystem falls back to copyWithProgress (events are harmless without a listener). Add the job modal only if large cross-disk moves feel stuck.

## Steps
- [ ] 1. IPC `rom:moveToConsoleFolder(slug)` in rom.ts: load /games/{slug}/device; require rom_source local and rom_path existing; folder = consoleLocalFolder(); skip if rom_path already under folder; dest = join(folder, basename); refuse if dest exists; mkdirSync; renameSync, on EXDEV copyWithProgress to .part + sha256 check + rename + unlink original; PUT {...gd, rom_path: dest, launch_command with old path replaced}.
  - Files: src/gui/electron/sync/rom.ts
  - Reuses: consoleLocalFolder, copyWithProgress, sha256OfFile, the rom:localize PUT/launch_command pattern (#518)
  - New: one handler - localize requires rom_source network and keeps the original, so it cannot be reused.
- [ ] 2. Expose the channel: preload.ts `rom.moveToConsoleFolder`, emusync.d.ts type.
  - Files: src/gui/electron/preload.ts, src/gui/renderer/src/emusync.d.ts
  - Reuses: rom.delocalize binding shape
- [ ] 3. UI: in NetworkRomPanel, for romSource local, fetch console folder (existing effect, drop the network-only guard) and show "Move to console folder" when romPath is outside it; on success call new prop `onRomPathChange(path, launchCommand)`. GameConfig passes romPath and a setter calling setRomPath/setLaunchCommand.
  - Files: src/gui/renderer/src/components/game-config/NetworkRomPanel.tsx, src/gui/renderer/src/components/GameConfig.tsx
  - Reuses: existing getDeviceConsoles lookup, romBusy/romMsg state, handleLocalize layout
  - New: none beyond the button and props.
- [ ] 4. Tests: no Python/API behaviour changes; no renderer test harness exists. Manual verification noted in PR.
- [ ] 5. Docs: ARCHITECTURE.md IPC list - add rom:moveToConsoleFolder.

## Testing
- **Test File**: none (no Python/API change; Electron main has no test harness). `make test-changed` must still pass; `npx tsc --noEmit` in src/gui for types.
- **Test Cases**: manual - local ROM outside folder shows button and moves; ROM inside folder shows none.
- **Edge Cases**: destination exists (refused); cross-filesystem (EXDEV copy path); no console folder set (error message).
- **Integration Points**: PUT /games/{slug}/device persists rom_path and launch_command.

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): yes. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
Progress/cancel modal; moving network-sourced ROMs; moving multi-file/directory ROMs (PS3 folders).

## Log
