# Handoff: #631 Re-path game when the console folder already has the ROM during move

## Metadata
- Issue: #631
- Branch: feature/631-repath-existing-console-rom
- PR: none
- Status: implementing
- Created: 2026-10-29
- Fix attempts: 0

## 1. Issue
### Summary
Moving a local ROM to its console folder fails with "A file with that name already exists in the console folder" when the file is already there (reported for "Pokemon Heart and Soul"). Nothing is re-pathed.
### Motivation
The user must fix the path by hand although the correct file is already in the console folder.
### Proposed Behavior / Steps to Reproduce
1. Local-source game whose ROM is outside `device_local_folder`; a same-named file already exists in that folder.
2. Use "Move to console folder" (MoveLocalRomPanel) or the bulk move from Refresh locations (LocalToNetworkModal).
3. Expected: game re-pathed to the existing file and validated; actual: error, no change.
### Affected Area
- src/gui/electron/sync/rom.ts (`rom:moveToConsoleFolder`, existsSync(dest) early return)
- src/gui/renderer/src/components/game-config/MoveLocalRomPanel.tsx
- src/gui/renderer/src/components/LocalToNetworkModal.tsx
- Related: #622, #626, #616
### Acceptance Criteria
- [ ] Existing destination file: game re-pathed to it (rom_path + launch command) instead of failing.
- [ ] Validated after re-path: file exists at new path and GET /games/{slug}/device shows the new rom_path; otherwise error.
- [ ] Panel and bulk modal both say an existing file was used.
- [ ] Source file is not deleted or overwritten on this path.
- [ ] Regression test or documented manual check.

## 2. Design
### Scope: Small. Electron main-process handler plus two message tweaks in the renderer; no server change.
User decisions: (1) adopt the existing file only when its byte size equals the source's, otherwise keep the current error; (2) leave the original file untouched.
### Backend Changes: none
### UI Changes: `rom:moveToConsoleFolder` (src/gui/electron/sync/rom.ts) adopts a same-size existing destination: PUT rom_path + launch command, re-GET and verify file exists and rom_path matches, return `adopted: true`. `emusync.d.ts` and `preload.ts` types gain optional `adopted`. `MoveLocalRomPanel` and `LocalToNetworkModal` show that an existing file was used.
### Plan Target: fplan
### Sub-issues: none
### Difficulty: 3/10
### Backwards Compatibility: no breaking changes; optional field on an existing IPC result.
## 3. Frontend Plan
### Design Alignment: Reuses the panel's inline status text; no new UI. Plan file: tools/plans/631-repath-existing-console-rom.md
### Visual Pattern: Existing muted status line next to the Move button reports the adopted result.
### Recommendations: none. LocalToNetworkModal (#626) is not on main yet; it needs no change.

## 4. Backend Plan
### Design Alignment: TBD
### Backend Pattern: TBD
### Recommendations: TBD

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: none automated (Electron main + React; no JS runner, no mocks). Manual script in the plan's Testing section plus tsc, make lint, make test-changed.
### Test Cases: adopt same-size existing file (path re-pointed, original kept), launch command rewritten, success only after verification re-read (3)
### Edge Cases: different size errors with no change; normal move still works; already-in-folder message; server unreachable gives ok:false (4)
### Integration Points: rom:moveToConsoleFolder -> PUT/GET /games/{slug}/device; MoveLocalRomPanel onMoved -> GameConfig; LocalToNetworkModal (#626) shares the channel

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps (fplan)
- 1. [done] rom.ts adopt path + post-PUT verification. Reuses existing GET/PUT, launchCommand line. New: `adopted` flag + verification GET (nothing validates stored config after a move).
- 2. preload.ts, emusync.d.ts: optional `adopted`. Reuses existing channel. New: none.
- 3. MoveLocalRomPanel.tsx message. Reuses setMsg/onMoved. New: none.
- 4. tsc + make lint + manual check (no JS test harness for Electron main).
- 5. CLAUDE.md (and ARCHITECTURE.md if applicable).

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
- 2026-10-29 issue: workflow initialized (issue #631 filed, handoff created; branched from main, independent of #629/PR #630)
- 2026-10-29 design: scope=ui, plan_target=fplan, difficulty=3/10, breaking=no
- 2026-10-29 fplan: 5 steps written, visual_pattern=reuse panel status line, no new UI
- 2026-10-29 tplan: test_file=none (manual script + tsc/lint), 3 test cases + 4 edge cases defined
- 2026-10-29 implement: step 1 done (adopt same-size existing file, verify stored path)
