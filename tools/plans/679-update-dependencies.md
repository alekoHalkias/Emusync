# Plan: #679 Audit and update dependencies

Issue: #679
Branch: feature/679-update-dependencies
PR: none
Status: implementing
Fix attempts: 0

## Goal
Remove unused dependencies and bring in-range dependencies current; hold major framework bumps for separate issues.

## Design Alignment
- **Backend Pattern**: manifests and lockfile only; no code pattern change.
- **Recommendations**: Audit found adm-zip unused (zero imports). Python deps (fastapi, uvicorn, httpx, click, tomlkit, zeroconf, pydantic, pytest, pytest-asyncio) are all used and the venv is current. Majors (Electron 31->45, electron-builder 24->26, electron-vite 2->6, vite 5->8, plugin-react 4->6, React 18->19, TypeScript 5->7) each risk breaking the build or AppImage; split into follow-up issues.

## Steps
- [x] 1. Remove adm-zip from src/gui/package.json and lockfile (`npm uninstall adm-zip`); re-grep to confirm no use in electron/, renderer/, scripts, and electron-builder config.
  - Files: src/gui/package.json, src/gui/package-lock.json
  - Reuses: n/a
  - New: none
- [x] 2. Update in-range npm deps (`npm update`: smol-toml 1.9.1, @types/react patch); raise the smol-toml caret floor to ^1.9.1.
  - Files: src/gui/package.json, src/gui/package-lock.json
  - Reuses: npm semver ranges
  - New: none
- [x] 3. Raise Python lower bounds to the versions currently verified in the venv (pip freeze), keeping >= style; no package additions or removals.
  - Files: src/requirements.txt, src/requirements-dev.txt
  - Reuses: existing format
  - New: none
- [x] 4. Verify: `make lint`, `make build-gui`, `make test`; bundle test must still pass.
  - Files: none
  - Reuses: Makefile targets
  - New: none
- [x] 5. Tests: no new tests; existing suite plus test_bundle.py cover requirements/packaging.
- [x] 6. Docs: none needed - no behavior, rule, or architecture change.
- [x] 7. File follow-up issues (one per major group: Electron+electron-builder+electron-vite, Vite+plugin-react, React 19 types, TypeScript 7) via `gh issue create`.

## Testing
- **Test File**: none new; existing src/tests suite and src/tests/test_bundle.py
- **Test Cases**:
  - full suite: `make test` passes on updated Python floors
  - test_bundle.py: packaging/requirements check still passes
- **Edge Cases**:
  - adm-zip removal: build-gui and electron-builder succeed (no hidden dynamic require)
- **Integration Points**:
  - make lint and make build-gui

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
Major version bumps of Electron, electron-builder, electron-vite, Vite, plugin-react, React, TypeScript.

## Log
