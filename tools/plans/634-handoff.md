# Handoff: #634 Auto-update: GUI checks and installs new releases from GitHub

## Metadata
- Issue: #634
- Branch: feature/634-auto-update
- PR: none
- Status: tplan done
- Created: 2026-01-03
- Fix attempts: 0

## 1. Issue
### Summary

Add automatic update checks so the EmuSync GUI detects and installs new releases from GitHub without requiring manual download and installation.

### Motivation

Users currently must manually check GitHub for new versions, download the AppImage/NSIS installer, and run it. This is error-prone and creates support burden. An auto-updater provides a seamless upgrade path.

### Proposed Behavior / Steps to Reproduce

- On app launch and at a configurable interval (default: every 4 hours), the GUI checks the latest GitHub release for a new version.
- If a newer version is available, the user is notified via a non-blocking UI element (e.g., a banner or settings notification).
- The user can trigger the update from the notification or from a settings panel.
- The update downloads the appropriate artifact (AppImage for Linux, NSIS installer for Windows) and installs it silently or with a brief confirmation dialog.
- The app restarts to apply the update.
- The Python server component (`src/emusync.py` and CLI) is NOT covered by this issue — it is distributed via `install.sh`/systemd and will require a separate mechanism.

### Affected Area

- `src/gui/package.json` (electron-builder `publish` config)
- `src/gui/electron/` (new auto-update module)
- `src/gui/electron/preload.ts` (expose update IPC to renderer)
- `src/gui/renderer/src/` (update notification UI, settings integration)
- `.github/workflows/release.yml` (generate update metadata)

### Acceptance Criteria

- [ ] GUI checks for updates on startup and at regular intervals
- [ ] User is notified when a new version is available
- [ ] User can trigger download and install from the notification
- [ ] Update installs the correct artifact for the current platform
- [ ] App restarts after update is applied
- [ ] Update checks are skipped when the user has disabled them in settings
- [ ] No update UI or logic touches the Python server component

## 2. Design
### Scope: Purely client-side (Electron main + renderer). No Python server changes.
### Backend Changes: None. `display.ts` gains `autoUpdateEnabled` field in the Display interface and `display:get`/`display:set` handlers.
### UI Changes: New `UpdateBanner.tsx` component, new `useUpdater.ts` hook, new `updater.ts` Electron main module. Settings toggle in ServerStatusButton Display section.
### Plan Target: fplan (frontend-only, no backend changes needed).
### Sub-issues: None — self-contained, ~8 files, moderate complexity.
### Difficulty: 6/10 — moderate. electron-updater integration, IPC wiring, React UI components. Well-scoped, no deep architectural changes.
### Backwards Compatibility: No breaking changes. New `display.json` key (`autoUpdateEnabled`, default `true`), new IPC channels (all additive). Existing installs unaffected.

## 3. Frontend Plan
### Design Alignment: Update banner reuses existing button classes (`btn`/`btn-ghost`/`btn-danger`) and CSS variables. Toggle lives in Display section of Settings modal alongside existing UI size/fullscreen/theme controls, using same `<label>` + checkbox pattern.
### Visual Pattern: Compact inline banner at top of app body, below header bar. Green accent for "update available", more prominent style for "update downloaded". Dismissible, reappears on next launch if update isn't installed.
### Recommendations: Banner is non-blocking — does not prevent navigation or interaction. "Restart now" button calls `app.relaunch()` IPC. Update check interval (4 hours) is electron-updater default, no UI toggle for it.

## 4. Backend Plan
### Design Alignment: N/A — no backend changes.
### Backend Pattern: N/A.
### Recommendations: N/A.

## 5. Merged Plan
### Conflicts Resolved: none — fplan-only (no bplan), self-contained frontend/Electron scope.
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: None — no JS test runner for Electron. Per `.claude/testing-guide.md` line 48-49: verified by `tsc` + `make lint` + manual script.
### Test Cases: 1) Update check fires on startup. 2) Banner appears when `update-available` event fires (inject in devtools). 3) Banner shows "Restart now" on `update-downloaded`. 4) "Restart now" calls `quitAndInstall()`. 5) Auto-update disabled → no check. 6) `update-not-available` → no banner. 7) Error event → banner shows error text. 8) TypeScript compilation passes.
### Edge Cases: No network → silent fail, no banner. Corrupt `latest.yml` → error in UI. Already downloaded update persists across relaunch. Toggle off mid-download → download continues (electron-updater behavior).
### Integration Points: electron-updater ↔ GitHub releases API (external). IPC: renderer ↔ main process (additive). Display settings ↔ `display.json` (new key `autoUpdateEnabled`).

## 7. Test Design
### Test Scope: Manual acceptance only. No automated tests.
### Test Types: Manual functional testing on Linux (AppImage) and Windows (NSIS).
### Test Cases: 1) On startup, verify update check fires. 2) When update available, verify banner appears. 3) "Restart now" applies update. 4) When disabled, no check fires. 5) When on latest, no banner.
### Affected Existing Tests: None.
### Implementation Checklist: Manual acceptance on Linux + Windows.

## 8. Implementation Steps
### Steps:
- [ ] 1. **Backend: add `electron-updater` dependency and configure GitHub publish.**
  - Files: `src/gui/package.json`
  - Add `"electron-updater": "^6.3.9"` to dependencies. Add `"publish": {"provider": "github", "repo": "alekoHalkias/Emusync"}` inside the `build` object.

- [ ] 2. **Electron main process: updater module.**
  - Files: `src/gui/electron/updater.ts` (NEW)
  - Wraps `electron-updater`'s `autoUpdater`. Registers IPC channels: `updater:check`, `updater:download`, `updater:install`, `updater:getEnabled`, `updater:setEnabled`. Listens to autoUpdater events and forwards via `win.webContents.send("updater:change", payload)`.

- [ ] 3. **Register updater IPC in main.ts.**
  - Files: `src/gui/electron/main.ts`
  - `import { registerUpdaterIpc } from "./updater";` + `registerUpdaterIpc();` after other register calls.

- [ ] 4. **Expose update IPC in preload.ts and types.**
  - Files: `src/gui/electron/preload.ts`, `src/gui/renderer/src/emusync.d.ts`
  - Add `updater` API to `window.emusync` namespace and type declarations. Add `updater:change` event to `ElectronAPI`.

- [ ] 5. **Settings toggle: auto-update switch in Display section.**
  - Files: `src/gui/electron/display.ts`, `src/gui/renderer/src/components/ServerStatusButton.tsx`
  - Add `autoUpdateEnabled` to Display interface, default `true`. Handle in `display:get`/`display:set`. Add checkbox toggle in ServerStatusButton Display section.

- [ ] 6. **React: update banner component and hook.**
  - Files: `src/gui/renderer/src/components/UpdateBanner.tsx` (NEW), `src/gui/renderer/src/hooks/useUpdater.ts` (NEW)
  - `useUpdater.ts`: subscribes to `updater:change` events, tracks state, provides check/download/install methods.
  - `UpdateBanner.tsx`: renders when update available/downloaded, shows version, "Restart now" and dismiss buttons.

- [ ] 7. **Integrate banner into app shell.**
  - Files: `src/gui/renderer/src/App.tsx`
  - Call `useUpdater` at App level, render `<UpdateBanner />` at top of app body.

- [ ] 8. **Release workflow: generate electron-updater metadata.**
  - Files: `.github/workflows/release.yml`
  - electron-updater's `latest.yml` generated automatically by electron-builder when `publish: github` is configured. No workflow changes needed.

- [ ] 9. **Tests:** No dedicated tests — electron-updater covers itself. Acceptance is manual.

- [ ] 10. **Docs: CLAUDE.md rules update.**
  - Files: `CLAUDE.md`
  - Note `display.json` gains `autoUpdateEnabled`. Note UpdateBanner component and `useUpdater` hook.

## 9. Review
### Findings: Schema bump: no. New IPC channel (+ emusync.d.ts): yes (updater:* + display:autoUpdateEnabled). New CLI subcommand: no. Config/data file change: yes (display.json gains `autoUpdateEnabled`).
### Blocked: none
### Blockers: none

## 10. Ship
### Status: pending
### PR: none
### Server Sync: pending
### Doc Sync: pending

## 11. Fix Attempts
### Attempt 1: none
### Attempt 2: none
### Attempt 3: none

## 12. Log
- 2026-01-03 issue: workflow initialized
- 2026-01-03 fplan: complete, frontend-only, 10 steps, 6/10 difficulty
- 2026-01-03 merge: fplan-only, no conflicts, status: planned
- 2026-01-03 tplan: test_file=none (manual), 8 test cases, 4 edge cases, tsc+lint+manual acceptance
