# Plan: #634 Auto-update: GUI checks and installs new releases from GitHub

Issue: #634
Branch: feature/634-auto-update
PR: none
Status: implementing
Fix attempts: 0

## Goal
Add automatic update checks so the EmuSync GUI detects and installs new releases from GitHub, with a user-controlled toggle and a non-blocking notification banner.

## Design Alignment
- **Visual Pattern**: The update banner reuses the existing `btn` / `btn-ghost` / `btn-danger` button classes and `var(--color-danger)` for urgency, matching the Settings modal's inline styling. The toggle lives in the Display section of the Settings modal alongside the existing UI size / fullscreen / theme controls, using the same `<label>` + checkbox pattern as "Watch for save changes" (line 419 of ServerStatusButton.tsx).
- **Recommendations**: Banner is dismissible (persists via state, not localStorage — it reappears on next launch if the update isn't installed). The "Restart now" button calls the `app.relaunch()` IPC. No modal — a compact inline banner at the top of the app body, below the header bar, consistent with how the existing server-status / activity elements sit in the page.

## Steps
- [x] 1. **Backend: add `electron-updater` dependency and configure GitHub publish.**
  - Files: `src/gui/package.json`
  - Reuses: existing `electron-builder` config (already present in package.json `build` field).
  - New: none — the `publish: "github"` entry tells electron-builder to upload artifacts and generate `latest.yml` for electron-updater at release time.
  - Changes: add `"electron-updater": "^6.3.9"` to dependencies. Add `"publish": {"provider": "github", "repo": "alekoHalkias/Emusync"}` inside the `build` object.

- [x] 2. **Electron main process: updater module.**
  - Files: `src/gui/electron/updater.ts` (NEW)
  - Reuses: `rt` from `./runtime` (for `mainWindow` reference), `ipcMain` pattern from `display.ts` / `config-store.ts`.
  - New: `src/gui/electron/updater.ts` — wraps `electron-updater`'s `autoUpdater`. Exposes `registerUpdaterIpc()` that registers:
    - `updater:check` — check for updates (returns `{ available: boolean, version?: string, error?: string }`)
    - `updater:download` — start download (returns `{ ok: boolean, error?: string }`)
    - `updater:install` — quit and install (calls `autoUpdater.quitAndInstall()`)
    - `updater:getEnabled` / `updater:setEnabled` — read/write `autoUpdateEnabled` from `display.json`
    - Listens to `autoUpdater` events (`update-available`, `update-downloaded`, `update-not-available`, `error`) and forwards them via `win.webContents.send("updater:change", payload)`.
  - Justification: no existing module handles background download/install lifecycle; must be a dedicated module.

- [x] 3. **Register updater IPC in main.ts.**
  - Files: `src/gui/electron/main.ts`
  - Reuses: the `register*Ipc()` import + call pattern already used by every domain module.
  - Changes: `import { registerUpdaterIpc } from "./updater";` + `registerUpdaterIpc();` after the other register calls.

- [x] 4. **Expose update IPC in preload.ts and types.**
  - Files: `src/gui/electron/preload.ts`, `src/gui/renderer/src/emusync.d.ts`
  - Reuses: existing preload pattern (`window.emusync.<domain> = { ... }`) and type declaration pattern.
  - Changes:
    - preload: add `updater: { check, download, install, getEnabled, setEnabled }` to the `emusync` namespace.
    - emusync.d.ts: add `interface UpdaterApi { check(): Promise<...>; download(): Promise<...>; install(): Promise<void>; getEnabled(): Promise<boolean>; setEnabled(enabled: boolean): Promise<boolean>; }` and add it to the `EmuSyncApi` interface.
    - Also add the `updater:change` event shape to `ElectronAPI` in emusync.d.ts.

- [x] 5. **Settings toggle: auto-update switch in Display section.**
  - Files: `src/gui/renderer/src/components/ServerStatusButton.tsx`
  - Reuses: existing `display` state pattern (loaded from `window.emusync.display`), checkbox toggle pattern (line 419: "Watch for save changes"), `window.emusync.display.*` IPC calls.
  - New: reads `autoUpdateEnabled` from the display settings via a new `display:getAutoUpdate` / `display:setAutoUpdate` IPC pair (or embeds it in the existing get/set). Actually, cleaner: add `autoUpdateEnabled` to the existing `display:get` return shape and `display:set` handler in `display.ts`. Then the toggle in ServerStatusButton reads/writes it alongside `scale`, `fullscreen`, `theme`.
  - Changes to `display.ts` (electron): add `autoUpdateEnabled: boolean` to the `Display` interface, default `true`, include in `display:get` response, handle in `display:set`.
  - Changes to ServerStatusButton.tsx: load `autoUpdateEnabled` from display state, add a checkbox toggle in the Display section, call `window.emusync.display.set` on change.

- [x] 6. **React: update banner component and hook.**
  - Files: `src/gui/renderer/src/components/UpdateBanner.tsx` (NEW), `src/gui/renderer/src/hooks/useUpdater.ts` (NEW)
  - Reuses: `btn` / `btn-ghost` / `btn-danger` classes, `RelTime` component for timestamps, existing IPC call patterns.
  - New:
    - `useUpdater.ts` hook: subscribes to `window.electron.on("updater:change", ...)` events, tracks `updateAvailable` (boolean), `updateVersion` (string), `updateDownloaded` (boolean), `error` (string). Provides `check()`, `download()`, `install()` methods.
    - `UpdateBanner.tsx`: a compact banner component that renders when `updateAvailable` or `updateDownloaded` is true. Shows version number, "Restart now" button (calls `install()`), and a dismiss button. Uses green accent for "update available" and a more prominent style for "update downloaded".
  - Justification: hook encapsulates IPC event subscription and state; banner is a self-contained presentational component. Both follow existing patterns (useGamepadNav, useEscapeToClose for hooks; Modal, ServerStatusButton for components).

- [x] 7. **Integrate banner into app shell.**
  - Files: `src/gui/renderer/src/App.tsx` (or the component that wraps the main layout — likely `GameGrid.tsx` or the top-level router)
  - Reuses: existing layout structure.
  - New: render `<UpdateBanner />` at the top of the app body, below the header. The `useUpdater` hook is called at the App level so update state is available throughout.
  - Changes: import `UpdateBanner` and `useUpdater`, call hook at App level, conditionally render banner.

- [x] 8. **Release workflow: generate electron-updater metadata.**
  - Files: `.github/workflows/release.yml`
  - Reuses: existing release workflow (already builds AppImage + NSIS, uploads to GitHub releases).
  - Changes: ensure the workflow sets `GH_TOKEN` and that electron-builder's `publish: "github"` config generates `latest.yml` and attaches it to the release. The existing workflow already handles uploads; electron-builder adds `latest.yml` automatically when `publish: github` is configured. No workflow changes needed if the `build` config in package.json is correct.

- [x] 9. **Tests:** No dedicated tests for the updater module — electron-updater's own test suite covers the library. The IPC wiring is integration-level and would require a running Electron app; the existing test suite (`src/tests/`) focuses on Python server / CLI / SQLite, not Electron renderer. Acceptance is manual: launch on each platform, verify update check, verify download prompt, verify restart.

- [x] 10. **Docs: CLAUDE.md rules update.**
  - Files: `CLAUDE.md`
  - Changes: add a note in the "Config / paths / DB" section about `display.json` gaining `autoUpdateEnabled`. Add a note in the "GUI" section about the UpdateBanner component and `useUpdater` hook. No ARCHITECTURE.md changes needed — the updater module is a new domain module, documented implicitly by the pattern.

## Testing
- **Test File**: None — no JS test runner exists for Electron renderer/main. Per `.claude/testing-guide.md` line 48-49, Electron-only changes are verified by `tsc` + `make lint` + manual script.
- **Test Cases**:
  - **Update check on startup**: Launch GUI, verify `autoUpdater.checkForUpdates()` fires (check via devtools console or IPC log).
  - **Banner appears when update available**: Simulate `update-available` event (inject `autoUpdater.emit("update-available", { version: "99.0.0" })` in devtools), verify banner renders with version and "Check for updates" / "Download" button.
  - **Banner shows download complete**: Simulate `update-downloaded` event, verify banner updates to "Restart now" state.
  - **Restart applies update**: Click "Restart now", verify `autoUpdater.quitAndInstall()` called (app quits).
  - **Auto-update disabled**: Toggle off in settings, verify no check fires on startup (no IPC call to `updater:check`).
  - **No banner on latest version**: Simulate `update-not-available` event, verify no banner.
  - **Error handling**: Simulate `error` event with message, verify banner shows error text.
  - **TypeScript compilation**: `tsc -p src/gui/electron/tsconfig.json && tsc -p src/gui/tsconfig.web.json` must pass with no errors.
- **Edge Cases**:
  - **No network**: Check silently fails, no banner shown.
  - **Corrupt `latest.yml`**: Error forwarded via IPC, shown in UI banner.
  - **Already downloaded update, relaunch**: Banner persists across restart until installed.
  - **Toggle during download**: Disable auto-update mid-download — download continues (electron-updater behavior), install only on explicit "Restart now".
- **Integration Points**: electron-updater ↔ GitHub releases API (external). IPC channels: renderer ↔ main process (all additive). Display settings ↔ `display.json` (new key).

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): yes (updater:* + display:autoUpdateEnabled). New CLI subcommand: no. Config/data file change: yes (display.json gains `autoUpdateEnabled`).

## Not in this plan
- Python server auto-update (explicitly out of scope per issue #634).
- Configurable check interval (default 4 hours baked into electron-updater; no UI toggle for the interval).
- Rollback / down-grade support.
- Beta / channel support (only checks `latest` release).

## Log

- [x] 11. **Fix (ship attempt 1):** `UpdateBanner.tsx` references undefined `releaseNotes` (tsc TS2304, runtime ReferenceError when an update is available) and imports unused `useCallback`. Destructure `releaseNotes` from `useUpdater()`, drop the unused import.

- [x] 12. **Review fixes:** attach updater listeners once and add a 4-hour re-check interval in updater.ts; remove stray root `emusync` script; restore tsbuildinfo files to main; document updater IPC in ARCHITECTURE.md.
