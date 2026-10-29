# Handoff: #618 Refresh locations: correct ROM source (local/network) from folder

## Metadata
- Issue: #618
- Branch: feature/618-refresh-rom-source (stacked on feature/616-game-location-refresh; PR #617 unmerged)
- PR: none
- Status: planned
- Created: 2026-10-29
- Fix attempts: 0

## 1. Issue
See https://github.com/alekoHalkias/Emusync/issues/618

## 2. Design
### Scope: Frontend-only. Extends useBrokenRoms.refresh (from #616) with a source check.
### Backend Changes: None. Uses PUT /games/{slug}/device and getDeviceConsoles (console rows carry device_game_folder, device_local_folder, device_network_folder).
### UI Changes: useBrokenRoms.ts (source check), GameGrid.tsx (toast text). Local = device_local_folder + device_game_folder; network = device_network_folder. Longest-prefix match wins; no match or no folders = unchanged. Network ROMs keep rom_rel_path/local_rom_path untouched.
### Plan Target: fplan
### Sub-issues: None.
### Difficulty: 3/10
### Backwards Compatibility: No breaking changes.

## 3. Frontend Plan
### Design Alignment: no new UI; reuses #616 toast. local = device_local_folder|device_game_folder, network = device_network_folder, longest prefix wins.
### Recommendations: see tools/plans/618-refresh-rom-source.md

## 4. Backend Plan
TBD

## 6. Testing Plan
### Test File: src/tests/test_game_location_refresh.py
### Test Cases: source flip to network, source flip to local (reuses _relink-style helper, client fixture)

## 8. Implementation Steps
1. sourceFor/relTo helpers in game-list/useBrokenRoms.ts (reuses norm; no containment helper exists).
2. refresh(deviceId) corrects rom_source via getDeviceConsoles + GET/PUT (reuses updateRom, api.ts).
3. GameGrid toast + deviceId from useDevices (reuses bulkMsg).
4. Tests in test_game_location_refresh.py (2 cases).
5. Docs: CLAUDE.md sentence.

## 9. Review
TBD

## 10. Ship
### Status: pending
### PR: none
### Server Sync: pending
### Doc Sync: pending

## 12. Log
- 2026-10-29 issue: workflow initialized, issue #618 created
- 2026-10-29 design: scope=ui, plan_target=fplan, difficulty=3/10, breaking=no
- 2026-10-29 fplan: 5 steps written, no new UI
- 2026-10-29 tplan: test_file=src/tests/test_game_location_refresh.py, 2 test cases defined
