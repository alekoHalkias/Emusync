# Plan: #650 Detect new games in local and network folders from the refresh button

Issue: #650
Branch: feature/650-refresh-detect-new-games
PR: none
Status: implementing
Fix attempts: 0

## Goal
Make Refresh locations also scan the console's local and network folders for ROMs not yet in the library, report the count, and offer to review and import them in the existing Add console wizard.

## Design Alignment
- **Visual Pattern**: the existing dismissible status line under the grid header (`bulkMsg`) carries the result; a small `btn btn-ghost` "Review and import" button sits inside it, matching the guide's inline status line pattern. The review itself reuses the Add console wizard modal, so no new modal.
- **Recommendations**: none. GameGrid.tsx is already 702 lines, so the scan logic goes in its own module and GameGrid only gains a call, one state value and a button.

## Steps
- [ ] 1. Let callers seed the wizard's roots: optional `initialNetworkRoot` and `initialLocalRoot` props, used in place of the saved config values in both detect paths of `useConsoleImport`, and passed through `ConsoleImport`. Without this a share found by Refresh would be imported as local-source when the config has no remembered network folder.
  - Files: src/gui/renderer/src/components/console-import/types.ts, useConsoleImport.ts, src/gui/renderer/src/components/ConsoleImport.tsx
  - Reuses: the existing `initialConsole` / `initialRomDirs` seeding and `setNetworkRoot` / `setLocalRomRoot`
  - New: two optional props - the wizard only reads roots from saved config today
- [ ] 2. `scanNewRoms(consoleKey, deviceId)` returning `{ status: "ok" | "nofolders" | "noemulator" | "error"; count; folders; networkRoot; localRoot }`: resolve the console's abbreviation and device row, build the folder list (ROM, extra, local and network folders, de-duplicated), pick the detected emulator whose label equals `device_emulator` (else the only option), run `emulator.scan`, drop ignored ROMs, merge network and local copies with `classifyByRoot` when a network folder is set, and count what `dedupeAndLink` leaves that has no `existingGameSlug`.
  - Files: src/gui/renderer/src/components/console-import/scanNewRoms.ts (new)
  - Reuses: `annotateRoms`, `classifyByRoot`, `dedupeAndLink` (helpers.ts), `loadIgnoredRoms` / `filterIgnored` (ignoredRoms.ts), `getDeviceConsoles`, `gamesOverview`, `emulator.detect` / `emulator.scan`
  - New: one function - the wizard does the same steps inline across hook state, so there is nothing callable without opening the wizard
- [ ] 3. Wire it into Refresh: after the existing checks, show "Checking folders for new games..." while scanning, then append "N new games found." (or nothing new / skipped reason) to the result message; when N > 0 render a "Review and import" button in the message bar that opens `ConsoleImport` with `initialConsole`, `initialRomDirs` = the scanned folders and the two roots; `onImported` calls `onChanged`. Scan failures do not break the existing result message.
  - Files: src/gui/renderer/src/components/GameGrid.tsx
  - Reuses: `handleRefreshLocations`, `bulkMsg`, `ConsoleImport`, `onChanged`
  - New: one `newRoms` state value and the button - nothing existing holds a follow-up action
- [ ] 4. Verification: renderer has no JS test runner, so check manually via `make dev-gui`: add a ROM to the local folder and one to the network folder, click Refresh and see the count, open the wizard from the button and import them; confirm an ignored ROM and an already imported ROM are not counted; confirm a console with no folders or no detected emulator says so and the old refresh message still appears.
- [ ] 5. Docs: CLAUDE.md GUI rule and ARCHITECTURE.md (scanNewRoms, the two new wizard props).
  - Files: CLAUDE.md, src/docs/ARCHITECTURE.md

## Testing
- **Test File**: none automated. The change is renderer-only and the renderer has no JS test runner; adding one is out of scope. Python suite is unaffected (`make test` must still pass in ship).
- **Test Cases** (manual, `make dev-gui`, covers plan step 4):
  - New ROM in the local folder: Refresh reports "1 new game found", Review and import opens the wizard on the right console with the folders listed.
  - New ROM on the network share: counted once, imports as network-sourced (wizard shows the network folder, from the seeded roots).
  - Same new ROM in both folders: counted once (merged by `classifyByRoot`).
  - ROM already imported on this device, and a ROM on the ignore list: not counted.
  - Nothing new: message says no new games and shows no button.
- **Edge Cases**:
  - Console with no configured folders: message says there are no folders to scan; existing refresh results still shown.
  - No detected emulator for the console: message says so, no crash.
  - Network share unmounted or scan throws: existing refresh message still appears plus a short "couldn't scan for new games" note.
  - Console has several detected emulators and `device_emulator` label matches none: first option is used, wizard still lets the user change it.
- **Integration Points**:
  - Keep `scanNewRoms` free of React state so a runner can cover it later.
  - Wizard seeding: confirm the new `initialNetworkRoot` / `initialLocalRoot` props override saved config only when passed, so the Add console and bulk library entry points behave exactly as before.

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
Auto-import without review; background or scheduled scans; scanning every console at once; naming the folders per result; a progress bar beyond the status text.

## Log
