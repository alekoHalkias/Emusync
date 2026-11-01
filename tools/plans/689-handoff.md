# Handoff: #689 Update Vite, plugin-react and electron-vite together

## Metadata
- Issue: #689
- Branch: feature/689-update-vite-toolchain
- PR: none
- Status: implementing
- Created: 2026-11-01
- Fix attempts: 0

## 1. Issue
### Summary
Move vite, @vitejs/plugin-react and electron-vite to current majors together; finishes #681 and #682.
### Motivation
electron-vite 2.x needs Vite 4/5; electron-vite 5 breaks type checking on Vite 5; v6 and plugin-react 6 need newer Vite. Cannot bump separately.
### Proposed Behavior / Steps to Reproduce
Bump to the newest compatible set, fix config/type breakage, verify AppImage and NSIS builds.
### Affected Area
src/gui/package.json, lockfile, electron.vite.config, tsconfig files, release workflow.
### Acceptance Criteria
- [ ] Packages on current compatible majors
- [ ] make lint, make build-gui, make test pass
- [ ] AppImage and NSIS builds succeed
- [ ] #681 and #682 can be closed

## 2. Design
### Scope: build tooling only (src/gui/package.json, lockfile, electron.vite.config.ts, workflows); no schema/API/IPC/config change
### Backend Changes: bump electron-vite 2.3.0 -> 6.0.0 (peer vite ^6||^7||^8), vite 5 -> 8.3.5, @vitejs/plugin-react 5.2 -> 6.1.2 (peer vite ^8 plus optional oxc/rolldown babel plugins). Node engine requirement ^20.19 || >=22.12: confirm CI node-version. electron.vite.config.ts is small (main/preload/renderer, rollupOptions input) and likely needs little change; Vite 8 uses Rolldown so check externalizeDepsPlugin, build.rollupOptions naming and chunk output.
### UI Changes: none expected
### Plan Target: bplan
### Sub-issues: none; fallback if plugin-react 6 is troublesome is electron-vite 6 + Vite 7 + plugin-react 5.x
### Difficulty: 6/10
### Backwards Compatibility: not breaking

## 12. Log
- 2026-11-01 issue: workflow initialized
- 2026-11-01 design: scope=build tooling, plan_target=bplan, difficulty=6/10, breaking=no
- 2026-11-01 bplan: 5 steps written, backend_pattern=build tooling only
- 2026-11-01 tplan: test_file=none new, 2 test cases defined

## 4. Backend Plan (summary)
Build tooling only; target electron-vite 6 / vite 8 / plugin-react 6, fallback Vite 7 + plugin-react 5.

## 8. Implementation Steps
1. Bump packages, fix config: package.json/lock, electron.vite.config.ts; reuses existing config; no new code.
2. Node 22 in release.yml; reuses existing steps.
3. Verify lint/build/test/tsc/electron-builder --dir.
4. Tests none. 5. Docs: CLAUDE.md Dependencies line.

## 6. Testing Plan (summary)
### Test File: none new
### Outline
Backend: bump set, Node 22 in CI, verify, docs. Tests: make test, build-gui, tsc, electron-builder --dir.
### Summary
Move the Vite toolchain to current majors together and require Node 22 in CI.
