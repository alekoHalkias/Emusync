# Plan: #664 Refresh locations reports games but they are not shown in the library

Issue: #664
Branch: feature/664-refresh-locations-games-not-shown
PR: none
Status: planned
Fix attempts: 0

## Goal
Games auto-linked from a matching network share during "Review and import" appear in the grid immediately, without requiring the wizard's Done button.

## Root cause
`useConsoleImport.linkShareGames` (#644) calls `setGameDevice` for each ROM found on a matching share and shows "N games linked", but never notifies the parent. `GameGrid` only reloads via `onImported` (= `onChanged`), which fires solely from the Done step button. Closing the wizard by any other route (X, Close, Cancel) leaves the grid stale, so the linked games are not shown.

## Design Alignment
- **Visual Pattern**: no visual change.
- **Recommendations**: none

## Steps
- [ ] 1. In `linkShareGames`, call `onImported()` after the links succeed (when `done.size > 0`) so the grid reloads right away.
  - Files: src/gui/renderer/src/components/console-import/useConsoleImport.ts
  - Reuses: existing `onImported` prop (GameGrid passes `onChanged`)
  - New: none
- [ ] 2. Tests: no renderer test harness exists; verify with `npm run typecheck`/lint in src/gui and manual check (Refresh locations, Review and import on a matching share, close with X, confirm games show in grid).
- [ ] 3. Docs: none needed - behavior fix only, no rule/IPC/config change.

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
Changing the "new games found" wording or the scan count.

## Log
