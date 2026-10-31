# Handoff: #654 Remove Big Picture mode from the GUI

## Metadata
- Issue: #654
- Branch: feature/654-remove-big-picture
- PR: none
- Status: planned
- Created: 2026-10-31
- Fix attempts: 0

## 1. Issue
### Summary
Remove Big Picture mode (console wheel, user themes, Big Picture display toggle) from the GUI.
### Motivation
Out of scope for the project; adds code, IPC, docs and maintenance cost.
### Proposed Behavior / Steps to Reproduce
Always render desktop console grid. Remove theme engine/import/protocol/IPC. Drop `bigPicture` and `theme` from display.json (old files must still load); keep fullscreen. Keep desktop gamepad nav, drop wheel handling. Remove colour-logo art if unused. Update docs.
### Affected Area
Renderer: ConsoleWheel, ConsoleGrid, ServerStatusButton, App, styles.css, themes/default.css, useGamepadNav, emusync.d.ts. Electron: themes.ts, themes/bundled, display.ts, preload.ts, art.ts, main.ts. Docs: CLAUDE.md, ARCHITECTURE.md, GOTCHAS.md.
### Acceptance Criteria
- [ ] No Big Picture or theme code, IPC, or CSS remain
- [ ] Desktop grid, gamepad nav and fullscreen still work
- [ ] Old display.json with bigPicture/theme keys loads
- [ ] make build-gui and make test pass
- [ ] Docs no longer reference Big Picture

## 2. Design
### Scope: ui (Electron main + renderer + docs)
### Backend Changes: none
### UI Changes: delete ConsoleWheel, ThemeImportModal, themes.ts and bundled themes, getConsoleLogo art, theme/bigPicture IPC and display fields, wheel branch in useGamepadNav, bp-* CSS; simplify ConsoleGrid, App, ServerStatusButton, display.ts, art.ts, main.ts, preload.ts, emusync.d.ts; update CLAUDE.md, ARCHITECTURE.md, GOTCHAS.md
### Plan Target: fplan
### Sub-issues: none
### Difficulty: 4/10
### Backwards Compatibility: not breaking; display.ts must ignore leftover bigPicture/theme keys in display.json; user theme folders left in place

## 3. Frontend Plan
### Design Alignment: pure removal; desktop grid becomes the only path
### Visual Pattern: none new; Settings popover loses theme select, topbar loses Themes button
### Recommendations: none

## 4. Backend Plan
### Design Alignment: TBD
### Backend Pattern: TBD
### Recommendations: TBD

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: none new (pure removal; no existing test covers the removed code)
### Test Cases: make build-gui passes; make test-changed passes
### Edge Cases: legacy display.json with bigPicture/theme loads; gamepad LB/RB modal tabs and d-pad focus unchanged
### Integration Points: preload.ts/emusync.d.ts in sync; grep finds no leftover Big Picture/theme references

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps: see tools/plans/654-remove-big-picture.md
1. Electron main (main.ts, display.ts, art.ts, preload.ts, delete themes.ts + bundled): reuses display.ts load/save/applyDisplay; no new code.
2. emusync.d.ts: delete theme/bigPicture/getConsoleLogo members; no new code.
3. Components (delete ConsoleWheel, ThemeImportModal; trim ConsoleGrid, ServerStatusButton, App): reuses ConsoleGrid desktop branch; no new code.
4. useGamepadNav.ts + styles.css: delete rotateWheel and bp/wheel CSS; no new code.
5. Verify with make build-gui and grep.
6. Tests: none new; make test-changed.
7. Docs: CLAUDE.md, ARCHITECTURE.md, GOTCHAS.md trimmed.

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
- 2026-10-31 design: scope=ui, plan_target=fplan, difficulty=4/10, breaking=no
- 2026-10-31 fplan: 7 steps written, visual_pattern=pure removal
- 2026-10-31 tplan: test_file=none, 2 test cases defined (build, suite) plus manual legacy-config check
