# Plan: #682 Update Vite and @vitejs/plugin-react to current majors

Issue: #682
Branch: feature/682-update-vite
PR: none
Status: implementing
Fix attempts: 0

## Goal
Bump @vitejs/plugin-react to the highest major compatible with electron-vite 2.3.0 and Vite 5; document that Vite 6+ is blocked on #681.

## Design Alignment
- **Backend Pattern**: manifest-only change.
- **Recommendations**: electron-vite 2.3.0 peers vite ^4 || ^5, so Vite stays on 5.x; plugin-react 5.2.0 is the highest supporting Vite 5 (6.x needs Vite 8).

## Steps
- [x] 1. Set @vitejs/plugin-react to ^5.2.0 in src/gui/package.json and refresh the lockfile.
  - Files: src/gui/package.json, src/gui/package-lock.json
  - Reuses: npm
  - New: none
- [x] 2. Verify: make lint, make build-gui, make test.
- [x] 3. Tests: none new; existing suite and build cover it.
- [x] 4. Docs: CLAUDE.md note that Vite 6+ and plugin-react 6 wait on electron-vite major (#681).

## Testing
- **Test File**: none new
- **Test Cases**: make build-gui succeeds; make test passes
- **Edge Cases**: none
- **Integration Points**: electron.vite.config.ts uses react() plugin

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
Vite 6/7/8, plugin-react 6 (blocked on #681).

## Log
