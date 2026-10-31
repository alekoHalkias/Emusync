# Plan: #668 Use a version-independent AppImage filename and show the version in the app

Issue: #668
Branch: feature/668-stable-appimage-name
PR: none
Status: planned
Fix attempts: 0

## Goal
Linux AppImage has a stable filename (Steam shortcut survives updates) and the running version is shown in the settings Details panel.

## Design Alignment
- **Visual Pattern**: one more label/value row in the existing "Details" grid in ServerStatusButton (same span styles as Device ID).
- **Recommendations**: none

## Steps
- [ ] 1. Linux artifactName becomes `${productName}-linux-x86_64.${ext}`; Windows unchanged.
  - Files: src/gui/package.json
  - Reuses: existing build.linux.artifactName
  - New: none
- [ ] 2. Add `updater:getVersion` IPC returning `app.getVersion()`.
  - Files: src/gui/electron/updater.ts, src/gui/electron/preload.ts, src/gui/renderer/src/emusync.d.ts
  - Reuses: existing `updater` IPC namespace and registerUpdaterIpc
  - New: one handler - nothing exposes the app version today
- [ ] 3. Show "Version" row in the Details grid, fetched on mount.
  - Files: src/gui/renderer/src/components/ServerStatusButton.tsx
  - Reuses: Details grid rows (Device ID / Data folder)
  - New: one useState + useEffect - no existing version state
- [ ] 4. Verify `latest-linux.yml` url/path uses the new name (electron-builder generates it from artifactName); release.yml globs `*.AppImage` so no change expected. Run `npm run build` in src/gui to typecheck.
  - Files: .github/workflows/release.yml (only if release job lists names)
  - Reuses: existing globs
  - New: none
- [ ] 5. Tests: no Python surface and no TS test harness; verify with `make test-changed` (falls back to full suite) plus `npm run build --prefix src/gui` (electron-vite build) and `npx electron-builder --linux --dir`-free check: confirm `artifactName` via `npm run dist --prefix src/gui` locally if feasible, else rely on CI release run.
- [ ] 6. Docs: CLAUDE.md release artifact name line and IPC list (`updater:getVersion`); src/docs/ARCHITECTURE.md updater IPC list.

## Testing
- **Test File**: none (no TS test harness; Python suite unaffected)
- **Test Cases**:
  - Build: `npm run build --prefix src/gui` succeeds, so the new IPC and preload types compile
  - Artifact: built AppImage is named `EmuSync-linux-x86_64.AppImage` and `latest-linux.yml` references it
- **Edge Cases**:
  - Existing versioned AppImage installs: auto-update replaces in place, path unchanged
- **Integration Points**:
  - Release job uploads `*.AppImage` and `latest-linux.yml` under the new name

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): yes. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
Windows installer rename; migrating existing versioned installs (they keep their path via in-place update).
## Log
