# Plan: #753 Replace launch command field with an emulator picker in game and console settings

Issue: #753
Branch: feature/753-emulator-picker
PR: none
Status: planned
Fix attempts: 0

## Goal
Game and console settings pick an installed emulator from a dropdown (plus Custom and More...), derive launch command and save/state paths from it, and optionally move existing saves to the new emulator's location.

## Design Alignment
- **Visual Pattern**: Settings-form `input-group` with a plain `<select>` (guide "Settings forms"); install rows reuse the wizard's `InstallOptions` (guide "Empty state with actions"); switch confirmation is a standard `Modal` with `modal-actions`.
- **Recommendations**: Console-level picker hides "Custom command" (a console has no single command). Moves are queued and run on Save in GameConfig, so cancelling the form never leaves files moved under an unsaved config.

## Rules applied
- Archive/state moves never delete or rename the target first; state files move individually (#692). Never overwrite an existing destination file; report it as skipped.
- Shared-layout consoles (`usesSharedSaveLayout`): per-game switch keeps `save_path` (the card); PS2 (`usesSharedStateLayout`) keeps `state_path` too. Card/sstates move only from the console-level picker, once per distinct source path.
- Switch/PS3 resolve a blank save path (learned after play, #441/#422): keep the current `save_path`.
- Launch command uses the `%ROM%` token (#518); built only in `scan.ts`, never duplicated in the renderer.
- New IPC channels go in `preload.ts` and `emusync.d.ts`.

## Steps
- [ ] 1. Extract per-ROM resolution in `scan.ts` into exported `resolveRomEntry(consoleKey, option, romPath, scanDir): RomEntry`; `runEmulatorScan` maps through it. No behavior change.
  - Files: src/gui/electron/emulator/scan.ts
  - Reuses: the existing `.map(romPath => {...})` body verbatim (matchSaveFile, resolveSharedCard, state lookup, launch command)
  - New: none (function boundary only)
- [ ] 2. IPC `emulator:resolveGame({ consoleKey, option, romPath, scanRoot })` returns `{ savePath, saveExists, statePath, stateExists, launchCommand }` from `resolveRomEntry` (scanRoot falls back to `dirname(romPath)`).
  - Files: src/gui/electron/emulator/ipc.ts, src/gui/electron/preload.ts, src/gui/renderer/src/emusync.d.ts
  - Reuses: step 1, `loadConsoleDefinitionsIfNeeded`
  - New: channel - scan only resolves whole folders, settings need one ROM
- [ ] 3. IPC `emulator:moveSaves({ fromSave, toSave, fromState, toState })` in new `emulator/moveSaves.ts`: save (file or folder) renamed, EXDEV falls back to `cpSync` into `<dest>.part`, verify, `renameSync`, then remove source; state folder moved file by file. Skips missing/same sources, never overwrites an existing destination. Returns `{ ok, moved: string[], skipped: string[], error? }`.
  - Files: src/gui/electron/emulator/moveSaves.ts, src/gui/electron/emulator/ipc.ts, src/gui/electron/preload.ts, src/gui/renderer/src/emusync.d.ts
  - Reuses: rename + EXDEV copy/verify pattern from `sync/rom.ts` `rom:moveToConsoleFolder`
  - New: file - `files:rename-game-files` renames by base name within one root and `rom:moveToConsoleFolder` is ROM/server-bound; files.ts is near the 300-line limit
- [ ] 4. Export the wizard install panel: `InstallOptions` takes `{ install, installCore, installFlatpak }` props instead of `vm`; add exported `SuggestionLinks({ suggestions })` (the existing linked list). `EmulatorStep` passes its vm fields. `SUGGESTION_LINKS` stays in EmulatorStep.tsx (test_emulator_suggestions.py reads it there).
  - Files: src/gui/renderer/src/components/console-import/EmulatorStep.tsx
  - Reuses: `InstallList`, `InstallOptions`, `SUGGESTION_LINKS`
  - New: none
- [ ] 5. New `game-config/EmulatorPicker.tsx`: `useEmulatorOptions(consoleKey)` (detect, `installCore`/`installFlatpak` then re-detect, same shape as useConsoleImport's), `matchOption(cmd, options)` (option whose `execPath` and, when set, `corePath` both appear in the command; else null = Custom), and `EmulatorPicker` (`<select>`: options by label, "Custom command" when `allowCustom`, "More..." toggling an inline panel with `InstallOptions` + `SuggestionLinks`).
  - Files: src/gui/renderer/src/components/game-config/EmulatorPicker.tsx
  - Reuses: `emulator.detect/installCore/installFlatpak` IPC, step 4 exports
  - New: component - no existing dropdown over detected options (ConsoleFoldersModal's is label-only, no install)
- [ ] 6. New `game-config/emulatorSwitch.ts`: `planSwitch({ consoleKey, option, romPath, scanRoot, savePath, statePath, sharedLayout, sharedStateLayout })` calls `emulator:resolveGame` and applies the rules above, returning `{ launchCommand, savePath, statePath, moveSave, moveState }`; `applyConsoleSwitch(abbr, consoleKey, option, options, move)` lists this device's games on the console (`listMyGameDevices` + `getGameDevice`), skips Custom (`matchOption` null), runs `moveSaves` once per distinct source, PUTs each via `setGameDevice({ ...cfg, launch_command, save_path, state_path })`, returns `{ updated, skipped, moveSkipped }`. Also a `previewConsoleSwitch` that returns the planned paths without writing, for the modal.
  - Files: src/gui/renderer/src/components/game-config/emulatorSwitch.ts
  - Reuses: `listMyGameDevices`, `getGameDevice`, `setGameDevice`, `usesSharedSaveLayout`/`usesSharedStateLayout`
  - New: module - shared by GameConfig and ConsoleFoldersModal, keeps GameConfig (692 lines) from growing
- [ ] 7. New `game-config/EmulatorSwitchModal.tsx`: warning "A save made with <old> may not load in <new>." and, when save/state paths change, "<new> uses save path <path> and state path <path>. Move existing save files there?" Actions: Cancel, Keep files, Move saves.
  - Files: src/gui/renderer/src/components/game-config/EmulatorSwitchModal.tsx
  - Reuses: `Modal`, guide modal pattern
  - New: component - SyncConflictModal is conflict-specific
- [ ] 8. GameConfig: replace the "Launch command" input with "Emulator" (`EmulatorPicker`, consoleKey from `emulator.consoles()` by abbr). On load select `matchOption(launchCommand)`; Custom shows the existing text input unchanged. On pick: `planSwitch` with the ROM in use and `rom_folder_path`, open `EmulatorSwitchModal`; on confirm set launch/save/state fields and keep the move in a ref; `handleSave` runs `moveSaves` before `setGameDevice` and aborts with the error on failure. Validation keeps "Launch command is required" for Custom only; a picked option always yields a command.
  - Files: src/gui/renderer/src/components/GameConfig.tsx
  - Reuses: steps 5-7, existing `handleSave`, `withRomToken`
  - New: none
- [ ] 9. ConsoleFoldersModal: replace the label select with `EmulatorPicker` (`allowCustom={false}`, value matched by `device_emulator` label). On pick: `previewConsoleSwitch`, `EmulatorSwitchModal` (shows the console's new save/state root, or the card path for shared layouts, plus game count); on confirm `applyConsoleSwitch`, set `device_emulator`, `device_save_folder` (card path for shared layouts, else `option.saveDir`), `device_state_folder` (`option.stateDir ?? ""`) and call the existing `save()`. Result in the existing `msg` line ("Switched N games, M saves moved, K skipped").
  - Files: src/gui/renderer/src/components/ConsoleFoldersModal.tsx
  - Reuses: steps 5-7, existing `save()` / `updateDeviceConsole`
  - New: none
- [ ] 10. Tests: see section 6/7 of the handoff (tplan).
- [ ] 11. Docs: ARCHITECTURE.md (IPC `emulator:resolveGame`, `emulator:moveSaves`; components EmulatorPicker, EmulatorSwitchModal, emulatorSwitch.ts), CLAUDE.md GUI rule for #753.

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): yes (emulator:resolveGame, emulator:moveSaves). New CLI subcommand: no. Config/data file change: no.

## Not in this plan
- Converting save formats between emulators (e.g. .srm vs .sav); the warning covers it.
- Windows/macOS auto-install (download links only, as in #744/#745).

## Log
- 2026-11-20 fplan: plan written
