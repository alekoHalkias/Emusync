# Handoff: #638 Fix release workflow failing on electron-builder publish

## Metadata
- Issue: #638
- Branch: feature/638-release-publish-fix
- PR: none
- Status: planned
- Created: 2026-10-30
- Fix attempts: 0

## 1. Issue
### Summary
Release workflow fails because electron-builder tries to publish during `npm run dist` (HttpError 404, run 41133474404) since #634 set `build.publish` to github.
### Motivation
No release can be produced; v0.7.0 is tagged but unreleased.
### Proposed Behavior / Steps to Reproduce
Build jobs run `electron-builder --publish never`; upload latest*.yml with the installers; release job attaches all of them.
### Affected Area
`.github/workflows/release.yml`, `src/gui/package.json`
### Acceptance Criteria
- [ ] Build jobs do not publish
- [ ] latest.yml and latest-linux.yml uploaded and attached to the release
- [ ] A v* tag produces a release with AppImage, NSIS installer, and metadata

## 2. Design
### Scope: CI/build only
### Backend Changes: None
### UI Changes: None
### Plan Target: bplan
### Sub-issues: None
### Difficulty: 2/10
### Backwards Compatibility: No breaking changes

## 3. Frontend Plan
### Design Alignment: TBD
### Visual Pattern: TBD
### Recommendations: TBD

## 4. Backend Plan
### Design Alignment: TBD
### Backend Pattern: TBD
### Recommendations: TBD

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: TBD
### Test Cases: TBD
### Edge Cases: TBD
### Integration Points: TBD

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps: see tools/plans/638-release-publish-fix.md (4 steps)
- Step 1: touches package.json; reuses dist script; no new code.
- Step 2: touches release.yml; reuses artifact steps; no new code.
- Step 3: no tests (CI-only).
- Step 4: touches CLAUDE.md; docs only.

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
- 2026-10-30 issue: workflow initialized
- 2026-10-30 design: scope=ci, plan_target=bplan, difficulty=2/10, breaking=no
- 2026-10-30 bplan: 4 steps written, backend_pattern=none (CI config)
