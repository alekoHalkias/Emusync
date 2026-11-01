# Plan: #689 Update Vite, plugin-react and electron-vite together

Issue: #689
Branch: feature/689-update-vite-toolchain
PR: none
Status: implementing
Fix attempts: 0

## Goal
Move vite, @vitejs/plugin-react and electron-vite to a mutually compatible current set so #681 and #682 can close.

## Design Alignment
- **Backend Pattern**: build tooling only; electron.vite.config.ts is small (main/preload/renderer with rollupOptions inputs) and is adjusted only if the new majors require it.
- **Recommendations**: Target set is electron-vite 6.0.0, vite 8.3.5, plugin-react 6.1.2. Fallback if plugin-react 6 or Rolldown cause trouble: electron-vite 6 + vite 7 + plugin-react 5.x. New engines require Node ^20.19 or >=22.12; release.yml pins node "20", so bump it to "22".

## Steps
- [x] 1. Bump packages: `npm install -D electron-vite@^6 vite@^8 @vitejs/plugin-react@^6` in src/gui; run `make build-gui`; fix config/type errors in electron.vite.config.ts only as needed. If Vite 8 set fails, fall back to the Vite 7 set and note it in the Log.
  - Files: src/gui/package.json, src/gui/package-lock.json, src/gui/electron.vite.config.ts
  - Reuses: existing config structure
  - New: none
- [x] 2. Set node-version "22" in both setup-node steps of the release workflow (new packages require Node ^20.19 or >=22.12).
  - Files: .github/workflows/release.yml
  - Reuses: existing steps
  - New: none
- [x] 3. Verify: `make lint`, `make build-gui`, `make test`, tsc for node and web configs (error count not above the existing 3), and an `npx electron-builder --dir` packaging check.
  - Files: none
  - Reuses: Makefile targets
  - New: none
- [x] 4. Tests: no new tests; existing suite and test_bundle.py cover packaging.
- [x] 5. Docs: update the Dependencies line in CLAUDE.md (Vite toolchain done, nothing held back).

## Testing
- **Test File**: none new; existing src/tests suite
- **Test Cases**:
  - make test passes
  - build output contains main, preload and renderer bundles
- **Edge Cases**:
  - Rolldown chunking: renderer bundle loads (check output size is sane vs 1,000 kB)
  - externalizeDepsPlugin still externalizes runtime deps for main
- **Integration Points**:
  - electron-builder --dir packaging; release workflow Node version

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
GUI smoke test of the packaged AppImage and NSIS build (manual, before release).

## Log
