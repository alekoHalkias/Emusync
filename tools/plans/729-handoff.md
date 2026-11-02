# Handoff: #729 Auto-link network-drive games on devices sharing the same network share

## Metadata
- Issue: #729
- Branch: feature/729-auto-link-network-games
- PR: none
- Status: implementing
- Created: 2026-11-02
- Fix attempts: 0

## 1. Issue
### Summary
A network-drive game set up on one device is never linked on another device whose console has the same `network_share_id` (#644/#660). The game stays "not on this device" there, and the only linking path is unreachable.

### Motivation
Both devices already have the share configured and verified against each other, and the server already stores the share-relative path (`rom_rel_path`). The game should become playable on the second device with no manual setup.

### Proposed Behavior / Steps to Reproduce
Repro: device A imports a network game (rom_rel_path set) from a share with a `.emusync-share-id` marker; device B configures the same console with the same share (same ID, any mount path); device B's grid still shows the game as not on this device, and Refresh locations doesn't link it.

Actual:
- Play is disabled for non-local games (`GameCard.tsx:134`), so `GameGrid.handlePlay` -> `NetworkPlaySetup` never opens.
- `NetworkPlaySetup.tryAutoImport` takes `scanResult.roms[0]` from a whole-mount scan (`NetworkPlaySetup.tsx:137`), which can link the wrong ROM.
- IPC `rom:setupNetworkPlay` (`gui/electron/sync/rom.ts:425`) already does the correct mount + rom_rel_path join, verification and PUT, but has no caller.

Proposed: for every game with a network source whose share_id equals one of this device's console network_share_id values and no config on this device, link it via the setupNetworkPlay logic using this device's device_network_folder (at least on Refresh locations; optionally on sync-daemon start / SSE game-added). Missing file = skip silently.

### Affected Area
- src/gui/renderer/src/components/GameGrid.tsx, GameCard.tsx, NetworkPlaySetup.tsx
- src/gui/electron/sync/rom.ts (rom:setupNetworkPlay)
- src/server/store/games.py (get_network_source_for_game), GET /games/{slug}/network-source
- possibly sync-daemon start / SSE handling

### Acceptance Criteria
- [ ] Matching-share games with no config on this device are linked automatically (at least on Refresh locations) via device_network_folder + rom_rel_path.
- [ ] File missing at the joined path: skipped, left unlinked, no error dialog.
- [ ] Unverified shares (blank network_share_id) never auto-link.
- [ ] NetworkPlaySetup no longer links scanResult.roms[0]; uses rom:setupNetworkPlay or the path is removed.
- [ ] Existing configs on the device are never overwritten.
- [ ] Tests cover share-ID match and skip cases.

## 2. Design
### Scope: backend+ui
### Backend Changes: New Store method `network_link_candidates(device_id)` in store/games.py (single query: games with a network-sourced game_devices row on another device, non-blank rom_rel_path, source console network_share_id equal to a non-blank network_share_id on this device's console of the same name, and no game_devices row for this device). Route `GET /devices/me/network-link-candidates` returning the portable fields of get_network_source_for_game plus this device's device_network_folder. No schema change.
### UI Changes: Extract the body of IPC rom:setupNetworkPlay (gui/electron/sync/rom.ts) into a reusable function; add IPC rom:autoLinkNetworkGames (fetch candidates, link each whose file exists at device_network_folder + rom_rel_path, skip missing, return linked count). Call from GameGrid Refresh locations (count in status message) and once on first grid load. Replace NetworkPlaySetup.tryAutoImport's scanResult.roms[0] with setupNetworkPlay. Add channel to preload.ts and emusync.d.ts.
### Plan Target: both
### Sub-issues: none
### Difficulty: 4/10
### Backwards Compatibility: not breaking. Additive route and IPC channel; rom:setupNetworkPlay signature unchanged; no schema/config changes; existing device configs never overwritten.

## 3. Frontend Plan
### Design Alignment: fits; no new UI, only an extra part in the Refresh locations status line.
### Visual Pattern: reuse setBulkMsg phrasing (plan: tools/plans/729-auto-link-network-games-frontend.md)
### Recommendations: move network-play code out of sync/rom.ts (552 lines) into sync/netplay.ts.

## 4. Backend Plan
### Design Alignment: fits; thin route over one inline-SQL method in the games mixin, read-only, no schema change. Route path changed from the design's `/devices/me/...` to `GET /games/network-link-candidates` to sit with `/games/overview`.
### Backend Pattern: store mixin method + thin APIRouter route (plan: tools/plans/729-auto-link-network-games-backend.md)
### Recommendations: register before `/games/{slug}` so the literal path is not taken as a slug.

## 5. Merged Plan
Plan file: tools/plans/729-auto-link-network-games.md
### Conflicts Resolved: docs steps from both plans merged (CLAUDE.md, ARCHITECTURE.md); backend route ordered before the Electron/renderer steps that call it.
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: src/tests/test_network_autolink.py (new; test_network_rom.py is 360 lines), reusing _add_game/_console_row/_set_share from tests.test_network_rom.
### Test Cases: match (B gets slug + mount_root + rel path, key set pinned); share mismatch; blank share either side; B already configured; A never sees own game; local source or blank rom_rel_path excluded.
### Edge Cases: two B console rows same share -> one candidate; B matching console with blank device_network_folder -> excluded.
### Integration Points: route resolves before /games/{slug}; payload keys consumed by rom:autoLinkNetworkGames. GUI verified by npm run build + manual two-device check.
### Outline:
Backend
- 1. Store.network_link_candidates(device_id): one query, matching share ID, no existing config on this device.
- 2. GET /games/network-link-candidates.
Frontend
- 3. Move rom:setupNetworkPlay into gui/electron/sync/netplay.ts, split out linkNetworkGame.
- 4. IPC rom:autoLinkNetworkGames (+ preload, emusync.d.ts): link every candidate whose file exists.
- 5. GameGrid: auto-link on grid load and on Refresh locations ("N network games linked.").
- 6. NetworkPlaySetup: use setupNetworkPlay instead of linking scan roms[0].
Tests
- 7. src/tests/test_network_autolink.py: 6 cases + 2 edge cases, real SQLite.
Docs
- 8. CLAUDE.md, src/docs/ARCHITECTURE.md.
### Summary: A network-drive game on one device is linked automatically on any device whose console network share ID matches, using its own mount + the stored relative ROM path.

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps (merged, tools/plans/729-auto-link-network-games.md)
1. Store network_link_candidates - src/server/store/games.py; reuses get_network_source_for_game join; new because that is per-slug.
2. Route GET /games/network-link-candidates - src/server/api/games.py; reuses _auth/_get_store.
3. Move setupNetworkPlay to gui/electron/sync/netplay.ts, split linkNetworkGame - rom.ts, netplay.ts, sync.ts; new module because rom.ts is 552 lines.
4. IPC rom:autoLinkNetworkGames - netplay.ts, preload.ts, emusync.d.ts; reuses linkNetworkGame.
5. GameGrid Refresh + mount-time call - GameGrid.tsx; reuses parts/setBulkMsg/onChanged.
6. NetworkPlaySetup uses setupNetworkPlay instead of roms[0] - NetworkPlaySetup.tsx.
7. Tests - src/tests/test_network_rom.py; build typecheck for GUI.
8. Docs - CLAUDE.md, src/docs/ARCHITECTURE.md.

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
- 2026-11-02 issue: workflow initialized
- 2026-11-02 design: scope=backend+ui, plan_target=both, difficulty=4/10, breaking=no
- 2026-11-02 bplan: 4 steps written, backend_pattern=store mixin method + thin route
- 2026-11-02 fplan: 6 steps written, visual_pattern=no new UI, Refresh status line part
- 2026-11-02 merge: 2 conflicts resolved, 0 unresolved
- 2026-11-02 tplan: test_file=src/tests/test_network_autolink.py, 8 test cases defined
