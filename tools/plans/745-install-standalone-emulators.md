# Plan: #745 Install standalone emulators from the import wizard

Issue: #745
Branch: feature/745-install-standalone-emulators
PR: none
Status: implementing
Fix attempts: 0

## Goal
On Linux with Flatpak, the import wizard's no-emulator state offers a one-click user-level Flatpak install of each standalone emulator the console supports, then re-detects.

## Design Alignment
- **Visual Pattern**: "Empty state with actions (#744)" in the design guide: label + `btn btn-ghost` Install, `spinner` while busy, 12px danger error under the row. Same block layout as `CoreInstallList`.
- **Recommendations**: none; no guide change needed.

## Steps
- [x] 1. `emulator:detect`'s `install` payload lists installable Flatpak standalones.
  - Files: src/gui/electron/emulator/detect.ts, src/gui/renderer/src/emusync.d.ts, src/gui/renderer/src/components/console-import/useConsoleImport.ts
  - Reuses: `coreInstallTargets` (add `standalones: Array<{ label: string; flatpakId: string }>` to `CoreInstallTargets`); the `flatpak list --app --columns=application` probe already in `detectEmulatorsForConsole` (hoist the memoised `getFlatpakList` to module scope so both use it; empty string = flatpak missing). Linux only (any arch: Flathub serves aarch64 too), so the early return for non-x64 must only gate cores. Include a standalone only when it has `flatpak_id`, flatpak is available, and the id is not already in the list. `NO_INSTALL` in `useConsoleImport.ts` and the `.d.ts` interface get `standalones: []`.
  - New: none.
- [x] 2. IPC `emulator:installFlatpak(consoleKey, flatpakId)`.
  - Files: src/gui/electron/emulator/installFlatpak.ts (new), src/gui/electron/emulator/ipc.ts, src/gui/electron/preload.ts, src/gui/renderer/src/emusync.d.ts
  - Reuses: `installCore.ts` shape (validate against `coreInstallTargets`, return `{ok:true}|{ok:false,error}`); `execFile` + `promisify` as in installCore.
  - New: `installFlatpak.ts` - core install is a download+unzip, nothing existing runs flatpak. Validates `flatpakId` is in `coreInstallTargets(home, consoleKey).standalones`; runs `flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo` then `flatpak install --user -y --noninteractive flathub <id>` (no shell, no sudo, 15 min timeout, `maxBuffer` 10 MB); error = last stderr line.
- [ ] 3. Wizard UI: "Install with Flatpak" rows.
  - Files: src/gui/renderer/src/components/console-import/EmulatorStep.tsx, src/gui/renderer/src/components/console-import/useConsoleImport.ts
  - Reuses: `CoreInstallList` busy/error state and row markup (generalise it into a small `InstallRow`-style list that takes `{key,label,run}` items, used for both cores and standalones, instead of duplicating); `installCore` in the hook as the template for `installFlatpak` (re-run `detectEmulators` on success).
  - New: `installFlatpak` in the hook - one-line twin of `installCore` for the new channel. Heading "Install an emulator (Flatpak)", button text "Install"; the core list keeps its heading.
- [ ] 4. Tests: src/tests/test_emulator_suggestions.py - every standalone `flatpak_id` in `consoles_data.py` matches a reverse-DNS app-id regex `^[A-Za-z][\w-]*(\.[A-Za-z_][\w-]*)+$` (it is passed as an argv to flatpak; validation in step 2 relies on these values). No TS test runner exists; manual check: `make build-gui` compiles.
- [ ] 5. Docs: CLAUDE.md "Missing emulator (#744)" bullet: replace "Standalone emulator install: #745." with the `install.standalones` field + `emulator:installFlatpak` (user-level Flathub, validated against the console's standalones, Linux only). ARCHITECTURE.md IPC list: add `emulator:installFlatpak`.

## Testing
- **Test File**: src/tests/test_emulator_suggestions.py (extend; same module guards consoles_data -> EmulatorStep/installCore contracts)
- **Test Cases**:
  - test_flatpak_ids_are_app_ids: every standalone `flatpak_id` in `_IMPORT_CONSOLES` matches the reverse-DNS app-id regex (they are passed as flatpak argv and are the allowlist installFlatpak.ts validates against)
- **Edge Cases**:
  - Standalone without `flatpak_id` (Eden): never listed, keeps its SUGGESTION_LINKS link (manual)
  - flatpak not on PATH / non-Linux: `standalones` empty, links only (manual)
  - Renderer passes an id not in the console's standalones: `{ok:false}` (manual, devtools `window.emusync.emulator.installFlatpak("ps2","org.evil.App")`)
- **Integration Points**:
  - Manual script: dev GUI on Linux with flatpak, `flatpak uninstall --user io.mgba.mGBA` if present, open import wizard for GBA with RetroArch absent, Install mGBA, wizard advances to emulator select listing "mGBA (Flatpak)". Then `flatpak uninstall --user io.mgba.mGBA`.
  - `make lint` + both tsc projects show no new errors beyond the known pre-existing list.

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): yes. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
- Windows installer execution (download links already cover Windows).
- Eden (no Flatpak on Flathub; keeps its download link).
- Streaming install progress percentages (spinner + error is enough).

## Log
- 2026-11-16 fplan: plan written
- 2026-11-16 tplan: 1 automated test case + manual script
Step 1: flatpak list not memoised at module scope (would go stale after install); new uncached flatpakApps() helper shared by both functions
