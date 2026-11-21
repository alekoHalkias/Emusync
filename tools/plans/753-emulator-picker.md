# Plan: #753 Replace launch command field with an emulator picker in game and console settings

Issue: #753
Branch: feature/753-emulator-picker
PR: none
Status: implementing
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
- [x] 1. Extract per-ROM resolution in `scan.ts` into exported `resolveRomEntry(consoleKey, option, romPath, scanDir): RomEntry`; `runEmulatorScan` maps through it. No behavior change.
  - Files: src/gui/electron/emulator/scan.ts
  - Reuses: the existing `.map(romPath => {...})` body verbatim (matchSaveFile, resolveSharedCard, state lookup, launch command)
  - New: none (function boundary only)
- [x] 2. IPC `emulator:resolveGame({ consoleKey, option, romPath, scanRoot })` returns `{ savePath, saveExists, statePath, stateExists, launchCommand }` from `resolveRomEntry` (scanRoot falls back to `dirname(romPath)`).
  - Files: src/gui/electron/emulator/ipc.ts, src/gui/electron/preload.ts, src/gui/renderer/src/emusync.d.ts
  - Reuses: step 1, `loadConsoleDefinitionsIfNeeded`
  - New: channel - scan only resolves whole folders, settings need one ROM
- [x] 3. IPC `emulator:moveSaves({ fromSave, toSave, fromState, toState })` in new `emulator/moveSaves.ts`: save (file or folder) renamed, EXDEV falls back to `cpSync` into `<dest>.part`, verify, `renameSync`, then remove source; state folder moved file by file. Skips missing/same sources, never overwrites an existing destination. Returns `{ ok, moved: string[], skipped: string[], error? }`.
  - Files: src/gui/electron/emulator/moveSaves.ts, src/gui/electron/emulator/ipc.ts, src/gui/electron/preload.ts, src/gui/renderer/src/emusync.d.ts
  - Reuses: rename + EXDEV copy/verify pattern from `sync/rom.ts` `rom:moveToConsoleFolder`
  - New: file - `files:rename-game-files` renames by base name within one root and `rom:moveToConsoleFolder` is ROM/server-bound; files.ts is near the 300-line limit
- [x] 4. Export the wizard install panel: `InstallOptions` takes `{ install, installCore, installFlatpak }` props instead of `vm`; add exported `SuggestionLinks({ suggestions })` (the existing linked list). `EmulatorStep` passes its vm fields. `SUGGESTION_LINKS` stays in EmulatorStep.tsx (test_emulator_suggestions.py reads it there).
  - Files: src/gui/renderer/src/components/console-import/EmulatorStep.tsx
  - Reuses: `InstallList`, `InstallOptions`, `SUGGESTION_LINKS`
  - New: none
- [x] 5. New `game-config/EmulatorPicker.tsx`: `useEmulatorOptions(consoleKey)` (detect, `installCore`/`installFlatpak` then re-detect, same shape as useConsoleImport's), `matchOption(cmd, options)` (option whose `execPath` and, when set, `corePath` both appear in the command; else null = Custom), and `EmulatorPicker` (`<select>`: options by label, "Custom command" when `allowCustom`, "More..." toggling an inline panel with `InstallOptions` + `SuggestionLinks`).
  - Files: src/gui/renderer/src/components/game-config/EmulatorPicker.tsx
  - Reuses: `emulator.detect/installCore/installFlatpak` IPC, step 4 exports
  - New: component - no existing dropdown over detected options (ConsoleFoldersModal's is label-only, no install)
- [x] 6. New `game-config/emulatorSwitch.ts`: `planSwitch({ consoleKey, option, romPath, scanRoot, savePath, statePath, sharedLayout, sharedStateLayout })` calls `emulator:resolveGame` and applies the rules above, returning `{ launchCommand, savePath, statePath, moveSave, moveState }`; `applyConsoleSwitch(abbr, consoleKey, option, options, move)` lists this device's games on the console (`listMyGameDevices` + `getGameDevice`), skips Custom (`matchOption` null), runs `moveSaves` once per distinct source, PUTs each via `setGameDevice({ ...cfg, launch_command, save_path, state_path })`, returns `{ updated, skipped, moveSkipped }`. Also a `previewConsoleSwitch` that returns the planned paths without writing, for the modal.
  - Files: src/gui/renderer/src/components/game-config/emulatorSwitch.ts
  - Reuses: `listMyGameDevices`, `getGameDevice`, `setGameDevice`, `usesSharedSaveLayout`/`usesSharedStateLayout`
  - New: module - shared by GameConfig and ConsoleFoldersModal, keeps GameConfig (692 lines) from growing
- [x] 7. New `game-config/EmulatorSwitchModal.tsx`: warning "A save made with <old> may not load in <new>." and, when save/state paths change, "<new> uses save path <path> and state path <path>. Move existing save files there?" Actions: Cancel, Keep files, Move saves.
  - Files: src/gui/renderer/src/components/game-config/EmulatorSwitchModal.tsx
  - Reuses: `Modal`, guide modal pattern
  - New: component - SyncConflictModal is conflict-specific
- [x] 8. GameConfig: replace the "Launch command" input with "Emulator" (`EmulatorPicker`, consoleKey from `emulator.consoles()` by abbr). On load select `matchOption(launchCommand)`; Custom shows the existing text input unchanged. On pick: `planSwitch` with the ROM in use and `rom_folder_path`, open `EmulatorSwitchModal`; on confirm set launch/save/state fields and keep the move in a ref; `handleSave` runs `moveSaves` before `setGameDevice` and aborts with the error on failure. Validation keeps "Launch command is required" for Custom only; a picked option always yields a command.
  - Files: src/gui/renderer/src/components/GameConfig.tsx
  - Reuses: steps 5-7, existing `handleSave`, `withRomToken`
  - New: none
- [x] 9. ConsoleFoldersModal: replace the label select with `EmulatorPicker` (`allowCustom={false}`, value matched by `device_emulator` label). On pick: `previewConsoleSwitch`, `EmulatorSwitchModal` (shows the console's new save/state root, or the card path for shared layouts, plus game count); on confirm `applyConsoleSwitch`, set `device_emulator`, `device_save_folder` (card path for shared layouts, else `option.saveDir`), `device_state_folder` (`option.stateDir ?? ""`) and call the existing `save()`. Result in the existing `msg` line ("Switched N games, M saves moved, K skipped").
  - Files: src/gui/renderer/src/components/ConsoleFoldersModal.tsx
  - Reuses: steps 5-7, existing `save()` / `updateDeviceConsole`
  - New: none
- [x] 10. Tests: new src/tests/test_move_saves.py drives `emulator/moveSaves.ts` through Node (type stripping) on real `tmp_path` files; existing test_emulator_suggestions.py must pass unchanged; both `tsc` projects + `make lint`; manual script below. No mocks.
  - Files: src/tests/test_move_saves.py, src/gui/electron/emulator/moveSaves.ts (keep it importing only `node:fs`/`node:path`, export `moveSaves`)
  - Reuses: `tmp_path`, #741 subprocess pattern (run a real program, assert result), test_emulator_suggestions.py as the EmulatorStep regression
  - New: test file - no harness exercises Electron main code; moveSaves is the only data-loss path in this change
- [x] 11. Docs: ARCHITECTURE.md (IPC `emulator:resolveGame`, `emulator:moveSaves`; components EmulatorPicker, EmulatorSwitchModal, emulatorSwitch.ts), CLAUDE.md GUI rule for #753.

## Review fixes
- [ ] R1. ConsoleFoldersModal confirmSwitch: device_save_folder/device_state_folder use the emulator root without the RetroArch core folder (`coreFolderName ? dirname(dir) : dir`, same as `scan.ts:resolveRomEntry`); shared layouts keep the card path.
  - Files: src/gui/renderer/src/components/ConsoleFoldersModal.tsx
- [ ] R2. ConsoleFoldersModal confirmSwitch: try/catch/finally so a failed apply clears the busy state, closes the modal and reports the error in the msg line.
  - Files: src/gui/renderer/src/components/ConsoleFoldersModal.tsx

## Testing
- **Test File**: src/tests/test_move_saves.py (skipped when `node` is missing or older than 22.18, which lacks default type stripping)
- **Test Cases**:
  - file move: save file moved to a new folder (parents created), source gone, bytes equal, reported in `moved`
  - folder move: folder save (GC card folder / Switch-style) moved whole, contents equal
  - state folder: each state file moved individually into the new folder; files already in the destination kept
  - same path: from == to is a no-op, nothing reported as moved
  - missing source: no error, nothing moved (fresh emulator, no save yet)
- **Edge Cases**:
  - destination exists: never overwritten; source untouched; path listed in `skipped`
  - state name collision: colliding file stays in the source folder, listed in `skipped`, others still move
  - blank paths: empty `fromSave`/`fromState` skip that half (shared-layout per-game switch)
- **Integration Points**:
  - test_emulator_suggestions.py: SUGGESTION_LINKS still parsed from EmulatorStep.tsx after the InstallOptions export
  - `PUT /games/{slug}/device` already accepts launch_command/save_path/state_path (covered by existing test_games.py/test_devices.py); no new server code
  - `tsc --noEmit` for main and renderer: no new errors beyond the known pre-existing ones
- **Manual script** (dev server + `make dev-gui`, real files in a temp ROM/save folder):
  1. GBA game with RetroArch mGBA core: Emulator shows the core; switch to standalone mGBA: modal shows warning + new save/state paths; Move saves; Save; save file is at the new path, config PUT matches, `emusync run` launches mGBA.
  2. Same, choose Keep files: paths updated, old files untouched.
  3. Cancel in the modal or leave the form unsaved: no files moved.
  4. Game with a hand-written command: opens as Custom with the text unchanged; saving keeps it.
  5. More...: install a missing core; the dropdown lists it without reopening.
  6. Console settings: switch a console with 2+ games and one Custom game; Custom game untouched, others updated, message counts correct; device_emulator/save/state folders updated.
  7. PS2 per-game switch: card and sstates paths unchanged; console-level switch moves the card once.

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): yes (emulator:resolveGame, emulator:moveSaves). New CLI subcommand: no. Config/data file change: no.

## Not in this plan
- Converting save formats between emulators (e.g. .srm vs .sav); the warning covers it.
- Windows/macOS auto-install (download links only, as in #744/#745).

## Log
- 2026-11-20 fplan: plan written
- 2026-11-20 tplan: testing section added
Step 6: no per-source dedupe in applyConsoleSwitch; once a shared card moves its source is gone, so later moves are no-ops.
Step 8: per-game picker state lives in new game-config/useGameEmulator.ts to keep GameConfig (692 lines) from growing; GameConfig falls back to the plain launch input when the game has no known console.
