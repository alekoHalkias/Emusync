# Handoff: #668 Use a version-independent AppImage filename and show the version in the app

## Metadata
- Issue: #668
- Branch: feature/668-stable-appimage-name
- PR: none
- Status: implemented
- Created: 2026-10-31
- Fix attempts: 0

## 1. Issue
### Summary
Linux AppImage artifact name embeds the version, breaking Steam non-Steam shortcuts on every update. Use a stable filename and show the version in the app.
### Motivation
Steam shortcut targets the exact AppImage path; version is only visible in the filename.
### Proposed Behavior / Steps to Reproduce
Stable Linux artifact name; version shown in GUI via IPC; release workflow, latest-linux.yml and updater (#634) keep working; auto-update keeps the AppImage path.
### Affected Area
src/gui/package.json (build.linux.artifactName), .github/workflows/release.yml, src/gui/electron/updater.ts, preload/emusync.d.ts, renderer settings/About, docs.
### Acceptance Criteria
- [ ] AppImage filename has no version
- [ ] latest-linux.yml and updater work with new name
- [ ] Auto-update keeps same path
- [ ] Version displayed in GUI
- [ ] Release workflow and docs updated

## 2. Design
### Scope: ui (Electron + build config)
### Backend Changes: none
### UI Changes: linux artifactName in src/gui/package.json; app:getVersion IPC (main, preload.ts, emusync.d.ts); show version in ServerStatusButton.tsx near the update toggle; verify release job asset upload and latest-linux.yml
### Plan Target: fplan
### Sub-issues: none
### Difficulty: 2/10
### Backwards Compatibility: not breaking; existing installs keep their versioned path (updater replaces in place); users re-add Steam shortcut once

## 3. Frontend Plan
### Design Alignment: extra row in existing Details grid
### Visual Pattern: same label/value spans as Device ID
### Recommendations: none

## 4. Backend Plan
### Design Alignment: TBD
### Backend Pattern: TBD
### Recommendations: TBD

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: none (no TS harness; Python suite unaffected)
### Test Cases: electron-vite build compiles; built artifact name is version-free and latest-linux.yml matches
### Edge Cases: existing versioned installs update in place
### Integration Points: release job asset upload
### Outline:
Frontend
- package.json: linux artifactName without version
- updater.ts/preload.ts/emusync.d.ts: updater:getVersion IPC
- ServerStatusButton.tsx: Version row in Details grid
Tests
- electron-vite build, make test-changed, verify artifact and latest-linux.yml name
Docs
- CLAUDE.md, ARCHITECTURE.md
### Summary: Linux AppImage gets a stable filename so Steam shortcuts survive updates, and the version is shown in the settings Details panel.

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps: see tools/plans/668-stable-appimage-name.md
1. package.json artifactName: reuses existing key, no new code
2. updater:getVersion IPC (updater.ts, preload.ts, emusync.d.ts): reuses updater namespace; one new handler, no existing version source
3. ServerStatusButton Details row: reuses grid; one useState/useEffect
4. verify latest-linux.yml and release.yml globs
5. typecheck only
6. docs: CLAUDE.md, ARCHITECTURE.md

## 9. Review
### Findings: TBD
### Blocked: TBD
### Blockers: TBD

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
- 2026-10-31 issue: workflow initialized
- 2026-10-31 design: scope=ui, plan_target=fplan, difficulty=2/10, breaking=no
- 2026-10-31 fplan: 6 steps written, visual_pattern=extra Details row
- 2026-10-31 tplan: test_file=none, 2 test cases defined
- 2026-10-31 implement: steps 1-6 done (stable AppImage name, updater:getVersion IPC, Version row, docs)
