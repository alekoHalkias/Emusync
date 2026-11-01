# Plan: #720 List all games with a minimal menu on the console tab

Issue: #720
Branch: feature/720-all-games-list
PR: none
Status: planned
Fix attempts: 0

## Goal
Show a flat "All games" list under the console cards on the home screen, each row with Play and a settings action.

## Design Alignment
- **Visual Pattern**: plain list rows using existing `btn`/`btn-ghost` classes and the `game-grid-section-label` heading; no new design pattern, guide unchanged.
- **Recommendations**: none

## Steps
- [ ] 1. New `AllGamesList` component: sorted rows (name, console label, Network/Local tag), a Play button (disabled unless `isLocal && !locked`) and a Settings button that opens the existing `GameModal`. Observable result: list renders from the `games` array.
  - Files: src/gui/renderer/src/components/AllGamesList.tsx
  - Reuses: GameModal + GameModalTarget (same target shape as GameGrid.openSettings), PlayIcon from icons.tsx, GameRow type
  - New: component - GameGrid is tied to a single console and cards; no flat-row list exists
- [ ] 2. Render it below the console grid and thread `onPlay`/`onChanged`/console-key resolver from App.
  - Files: src/gui/renderer/src/components/ConsoleGrid.tsx, src/gui/renderer/src/App.tsx
  - Reuses: ConsoleGrid's abbrToDef map (resolves a game's console to its key for GameModal), App.handlePlay, App.reload(true)
  - New: two optional props on ConsoleGrid - it owns the console-def lookup, so the list goes there
- [ ] 3. Styles for the rows (flex row, gap, border) in styles.css next to `.console-grid`.
  - Files: src/gui/renderer/src/styles.css
  - Reuses: existing CSS variables
  - New: `.all-games-*` rules - none existing for list rows
- [ ] 4. Tests: renderer has no test harness; verify manually with `make dev-gui` (offline cache path included) and run `make test-changed`.
- [ ] 5. Docs: none needed - small UI addition, no IPC/config/schema change.

## Testing
- **Test File**: none - the renderer has no component test harness and the change adds no backend code; guide reuses `make test-changed` as the gate.
- **Test Cases**:
  - Manual: home screen lists all games sorted by name; Play launches a local game; Settings opens GameModal.
- **Edge Cases**:
  - Remote-only or locked game: Play disabled.
  - Server offline: list renders from the cached rows.
  - No games: existing empty state only, no empty list.
- **Integration Points**:
  - GameModal onChanged -> App.reload(true) refreshes the list.

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
Search/filter, push/pull or device actions in the list, pagination.

## Log
