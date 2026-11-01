# Handoff: #675 Fix Steam shortcuts targeting the AppImage temporary mount path

## Metadata
- Issue: #675
- Branch: feature/675-steam-appimage-mount-path
- PR: none
- Status: planned
- Created: 2026-11-01
- Fix attempts: 0

## 1. Issue
### Summary
Steam shortcuts created from the AppImage point at /tmp/.mount_*/resources/emusync, which is removed on exit.
### Motivation
Shortcuts break after EmuSync closes.
### Proposed Behavior / Steps to Reproduce
Add a game to Steam from the AppImage; inspect shortcut exe. Expected: stable launcher path.
### Affected Area
src/gui/electron/steam.ts, runtime.ts, paths.ts
### Acceptance Criteria
- Shortcuts use a stable path across restarts and updates
- Stale /tmp/.mount_* exe entries corrected on next add/refresh
- Non-AppImage behavior unchanged
- Regression test or manual check

## 2. Design
### Scope: electron main only
### Backend Changes: none
### UI Changes: add launcherPath() in runtime.ts; use it in steam.ts (4 sites) and game.ts launcher:path; stable launcher when running from AppImage (APPIMAGE env / /tmp/.mount_ path). Open question: extraResources bundling vs configured repo path; electron-builder has no extraResources, emusync.py/emusync not bundled.
### Plan Target: fplan
### Sub-issues: none
### Difficulty: 5/10
### Backwards Compatibility: not breaking; ourSlug matches by basename so stale shortcuts are rewritten by addGame

## 3. Frontend Plan
### Design Alignment: no UI; errors reuse {ok,error}. User decision: AppImage uses repo checkout via EMUSYNC_SCRIPT.
### Visual Pattern: none
### Recommendations: none

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
### Outline: TBD
### Summary: TBD

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps
1. runtime.ts: add launcherPath() (null inside AppImage mount). Reuses SCRIPT. New helper replaces 5 duplicated joins.
2. steam.ts (4 sites) + game.ts: use launcherPath(); addGame errors when null; read-only handlers fall back so stale entries match and are rewritten on next add. Reuses ourSlug/isOurShortcut, {ok,error}.
3. Tests: manual check only; no TS harness exists; existing wrapper test covers the script.
4. Docs: CLAUDE.md rule.

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
- 2026-11-01 issue: workflow initialized
- 2026-11-01 design: scope=ui, plan_target=fplan, difficulty=5/10, breaking=no
- 2026-11-01 fplan: 4 steps written, visual_pattern=none
