# Plan: #681 Update Electron, electron-builder and electron-vite to current majors

Issue: #681
Branch: feature/681-update-electron-majors
PR: none
Status: implemented
Fix attempts: 0

## Goal
Bump electron to 45, electron-builder to 26, electron-vite to 5 (latest supporting the current Vite 5).

## Design Alignment
- **Backend Pattern**: manifest-only, plus build-config fixes if breakage appears.
- **Recommendations**: electron-vite 6 requires Vite >= 6, which is #682; use electron-vite 5 here and bump to 6 with #682.

## Steps
- [x] 1. Bump electron ^45, electron-builder ^26, electron-vite ^5; update allowScripts electron version key; npm install.
  - Files: src/gui/package.json, src/gui/package-lock.json
  - Reuses: npm
  - New: none
- [x] 2. Fix breakage in electron.vite.config.ts / main-process code if build, tsc or lint fails.
  - Files: src/gui/electron.vite.config.ts, src/gui/electron/*
  - Reuses: existing config
  - New: none
- [x] 3. Verify: tsc node+web, make lint, make build-gui, electron-builder dir build, make test.
- [x] 4. Tests: none new; existing suite and test_bundle.py.
- [x] 5. Docs: CLAUDE.md dependency note.

## Testing
- **Test File**: none new; existing suite
- **Test Cases**: make test, tsc, build-gui, electron-builder --dir
- **Edge Cases**: extraResources bundle still present in unpacked output
- **Integration Points**: Electron main APIs on v45

## Checklist
Schema bump: no. New IPC channel: no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
electron-vite 6 (needs Vite 6+, #682).

## Log
Step 1-2: electron-vite left at 2.x: v5 fails type-check on Vite 5 (rollupOptions missing from BuildEnvironmentOptions), v6 needs Vite 6+. Moves to #682. No config changes needed.
