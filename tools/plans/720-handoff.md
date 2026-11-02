# Handoff: #720 List all games with a minimal menu on the console tab

## Metadata
- Issue: #720
- Branch: feature/720-all-games-list
- PR: #721
- Status: implementing
- Created: 2026-11-01
- Fix attempts: 0

## 1. Issue
### Summary
Add an "All games" section to the console tab (home page) listing every game with a minimal game menu.
### Motivation
Reaching a game currently requires choosing a console first.
### Proposed Behavior / Steps to Reproduce
Below the console cards, list all games (name, console, local/network); per-row menu with Play, configure, go to console. Reuses the loaded `games` list; no new endpoint.
### Affected Area
ConsoleGrid.tsx (or sibling), App.tsx, game-list/.
### Acceptance Criteria
- [ ] Console tab shows list of all games below console cards.
- [ ] Each game has minimal menu with Play and configure actions.
- [ ] Empty state preserved.
- [ ] Works with offline cache fallback (#464).

## 2. Design
### Scope: ui only
### Backend Changes: none
### UI Changes: new list section under ConsoleGrid in App.tsx games screen; reuse games, handlePlay, setScreen
### Plan Target: fplan
### Sub-issues: none
### Difficulty: 2/10
### Backwards Compatibility: no breaking changes

## 3. Frontend Plan
### Design Alignment: existing btn/btn-ghost and section-label patterns; guide unchanged
### Visual Pattern: flat list rows, no new pattern
### Recommendations: none

## 4. Backend Plan
### Design Alignment: TBD
### Backend Pattern: TBD
### Recommendations: TBD

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: none (no renderer harness; manual verify + make test-changed)
### Test Cases: manual list/play/settings check
### Edge Cases: locked/remote game, offline cache, no games
### Integration Points: GameModal onChanged -> reload(true)
### Outline
Frontend: 1 AllGamesList.tsx (new, reuses GameModal); 2 ConsoleGrid/App wiring; 3 styles.css
Tests: 4 manual verify + make test-changed; 5 docs none
### Summary: Home screen gains a flat all-games list with Play and Settings per row.

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps: see tools/plans/720-all-games-list.md
- Step 1: AllGamesList.tsx (new); reuses GameModal, PlayIcon, GameRow; new because no flat list exists
- Step 2: ConsoleGrid.tsx, App.tsx; reuses abbrToDef, handlePlay, reload
- Step 3: styles.css; reuses CSS vars; new .all-games-* rules
- Step 4: manual verify + make test-changed
- Step 5: docs none

## 9. Review
### Findings: none
### Blocked: no
### Blockers: none

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
- 2026-11-01 design: scope=ui, plan_target=fplan, difficulty=2/10, breaking=no
- 2026-11-01 fplan: 5 steps written, visual_pattern=flat list rows reusing btn classes
- 2026-11-01 tplan: test_file=none, 3 manual cases defined
- 2026-11-01 implement: steps 1-5 done (AllGamesList, ConsoleGrid wiring, styles; tsc clean, 666 tests pass; manual GUI check not run)
- 2026-11-01 review: 0 findings, blocked=no
- 2026-11-01 fix-plan: user rejected flat list; replacing with All games console card (F1.1-F1.3)
