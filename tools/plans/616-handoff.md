# Handoff: #616 Add game-location refresh tool with broken-ROM detection and auto-re-link

## Metadata
- Issue: #616
- Branch: feature/616-game-location-refresh
- PR: none
- Status: implementing
- Created: 2025-10-29
- Fix attempts: 0

## 1. Issue
### Summary
Add a game-location refresh tool that validates ROM paths on demand and during the launch flow. Games with missing ROMs are visually flagged in the game list. When a user tries to run a game whose ROM path no longer exists, they are prompted to locate the game on disk; if found, the path is auto-updated and the game launches. The chosen folder is saved as a potential library path and a background scan auto-fixes other games whose ROMs now live there.

### Motivation
Users frequently reorganize ROM folders, move drives, or change emulator install locations. When that happens EmuSync's stored `rom_path` values go stale but the game still appears in the list with no warning. The user only discovers the breakage at launch time, and even then there is no built-in way to re-link — they must manually edit every game's device config or re-import from scratch.

### Proposed Behavior
- **Refresh button**: Scan all games on the current device, flag missing ROMs with a red exclamation point badge.
- **Broken-rom launch flow**: When Play is clicked on a game with a missing ROM, prompt the user to locate the file; update path and launch.
- **Background scan**: After re-linking, scan the new folder (and siblings) for other ROMs; auto-fix broken references; show toast summary.

### Affected Area
- **Backend**: None required for v1. Validation is client-side; updates use existing `PUT /games/{slug}/device`.
- **Frontend**: GameCard (new badge), GameGrid (refresh button + broken-rom launch guard), new modal for re-link flow, background scan orchestration via IPC.
- **GUI Electron**: Reuse existing dialog IPC; add `config:addRecentFolder` call.

### Acceptance Criteria
- [ ] A "Refresh locations" button scans all games and flags broken ROMs with a red exclamation point badge.
- [ ] Games with valid ROMs are unaffected.
- [ ] Play on a broken-rom game opens a modal prompting file location.
- [ ] Selected ROM updates `rom_path` and launches immediately.
- [ ] Folder is saved as a recent import folder for the console.
- [ ] Background scan auto-fixes other broken references with toast summary.
- [ ] Red exclamation badge is visually distinct and does not break layout.
- [ ] No schema changes or new IPC channels required.

## 2. Design
### Scope: Frontend-only for v1. No backend/schema/API/IPC changes.
### Backend Changes: None. Validation is client-side file-existence check; updates use existing PUT /games/{slug}/device.
### UI Changes: GameCard (new red exclamation badge), GameGrid (refresh button + broken-rom launch guard), new LocationResolverModal component, GameRow type augmentation.
### Plan Target: fplan (frontend-only)
### Sub-issues: None.
### Difficulty: 5/10 — moderate frontend complexity (new modal, badge, orchestration), contained scope.
### Backwards Compatibility: No breaking changes. All data in existing tables; existing endpoints and IPC channels reused.

## 3. Frontend Plan
### Design Alignment: Follow existing badge patterns (game-card-badge overlay, top-right corner) and modal patterns (Modal.tsx wrapper, NetworkPlaySetup body). New badge: red `!` circle, same size as existing badges.
### Visual Pattern: GameCard overlay badges (line 82-111 of GameCard.tsx). New badge uses `game-card-badge game-card-badge-broken` with red `#e5484d` background, white `!` icon. Same 16x16 badge size, same border-radius.
### Recommendations:
- Add `files:exists` IPC (simple `existsSync` wrapper in files.ts) for the refresh batch check.
- Add `isBrokenLocation: boolean` to GameRow type; GameCard checks it and shows the red exclamation badge.
- Refresh button goes in GameGrid header (after the gear/folders button, before the "Select All" button).
- LocationResolverModal: uses `dialog:openFile` for single-file ROMs, `dialog:openFolder` for Switch-style folder ROMs. Pre-filters by console ROM extensions.
- After re-link, derive save_path/state_path using existing heuristics from `electron/emulator/scan.ts` (matchSaveFile pattern, content-dir subfolder logic).
- After re-link, persist the found folder via `config:addRecentFolder` IPC.
- Background scan: after re-link, call `emulator:scan` IPC on the found folder + its siblings; match results against existing broken games on this device; auto-update their rom_path silently.
- Show a brief toast after background scan: "Found X additional ROMs."
- No new schema, no new API endpoints, no new game-list types beyond `isBrokenLocation`.

## 4. Backend Plan
### Design Alignment: TBD
### Backend Pattern: TBD
### Recommendations: TBD

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: src/tests/test_game_location_refresh.py
### Test Cases:
- Refresh detects missing rom_path
- Refresh ignores existing rom_path
- Re-link updates rom_path via PUT /games/{slug}/device
- Re-link updates rom_path with network source
- Save/state path derivation matches import-wizard heuristics
### Edge Cases:
- Broken rom on other device (isLocal=false, should not flag)
- Switch folder-based ROM (folder path accepted)
- Re-link preserves other fields (launch_command, save_path, state_path)
### Integration Points:
- PUT /games/{slug}/device endpoint (real SQLite)
- Store set_game_device method (round-trip verification)

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps:
1. Add `files:exists` IPC in `electron/files.ts` — `existsSync` wrapper returning boolean.
2. Add `isBrokenLocation` field to `GameRow` type in `game-list/types.ts`.
3. Update `emusync.d.ts` to declare `emusync.files.exists(path)`.
4. Add red exclamation badge to GameCard.tsx — new `game-card-badge-broken` overlay.
5. Add CSS for `.game-card-badge-broken` in `styles.css`.
6. Add "Refresh locations" button to GameGrid.tsx header — batch `files:exists` check, toast summary.
7. Create LocationResolverModal.tsx — file/folder picker, API update, save/state derivation, `config:addRecentFolder`.
8. Integrate LocationResolverModal into GameGrid.tsx — guard `onPlay`, re-link callback.
9. Add background scan after re-link — `emulator:scan` IPC, match broken games, auto-update.
10. Tests: integration tests for refresh detection, re-link API, background scan matching.
11. Docs: CLAUDE.md GUI section, ARCHITECTURE.md IPC section.

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
- 2025-10-29 issue: workflow initialized, issue #616 created
- 2025-10-29 design: scope=frontend-only, plan_target=fplan, difficulty=4/10, breaking=no
- 2025-10-29 fplan: 11 steps written, visual_pattern=red exclamation badge on game card
- 2025-10-29 tplan: test_file=src/tests/test_game_location_refresh.py, 5 test cases + 3 edge cases defined
- 2026-10-29 implement: steps 1-3 done (files:exists IPC + preload bridge, d.ts, isBrokenLocation on GameRow)
