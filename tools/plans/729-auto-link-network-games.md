# Merged Plan: #729 Auto-link network-drive games on devices sharing the same network share

Source plans: tools/plans/729-auto-link-network-games-frontend.md, tools/plans/729-auto-link-network-games-backend.md
Branch: feature/729-auto-link-network-games
PR: none
Status: planned
Fix attempts: 0

## Goal
A network-drive game set up on one device is linked automatically on any other device whose console has the same network share ID, via one server query and the existing (currently uncalled) `rom:setupNetworkPlay` logic.

## Steps
- [ ] 1. Store method `network_link_candidates(device_id) -> list[dict]` in `src/server/store/games.py`. One query: `game_devices gd` (rom_source='network', rom_rel_path != '', device_id != me) JOIN `games g` JOIN `consoles src` (src.device_id = gd.device_id, src.console_name = g.console, src.network_share_id != '') JOIN `consoles mine` (mine.device_id = me, mine.console_name = g.console, mine.network_share_id = src.network_share_id, mine.device_network_folder != ''), WHERE NOT EXISTS a `game_devices` row for (g.slug, me); `GROUP BY g.slug` with `MAX(gd.rowid)`. Returns `slug, console, rom_path, rom_rel_path, launch_command, save_path, state_path, share_id, mount_root`.
  - Files: src/server/store/games.py
  - Reuses: columns/share join of `get_network_source_for_game`
  - New: method - existing one is per-slug and does not filter by this device's share or existing config.
- [ ] 2. Route `GET /games/network-link-candidates` in `src/server/api/games.py`, before `GET /games/{slug}`; `_auth`, returns the Store list.
  - Files: src/server/api/games.py
  - Reuses: `_auth`, `_get_store`, `/games/overview` placement
- [ ] 3. Move `rom:setupNetworkPlay`, `tailSegments`, `consoleSaveStateFolders` from `gui/electron/sync/rom.ts` to new `gui/electron/sync/netplay.ts`; split the handler body into `linkNetworkGame(slug, src, mountRoot)` (rel-path safety check, `existsSync`, path rewrite, `PUT /games/{slug}/device`). `rom:setupNetworkPlay` keeps its signature. Export `registerNetPlayIpc()`, called from `gui/electron/sync.ts`.
  - Files: gui/electron/sync/rom.ts, gui/electron/sync/netplay.ts, gui/electron/sync.ts
  - Reuses: existing handler body, `loadServerCfg`
  - New: netplay.ts - rom.ts is 552 lines.
- [ ] 4. IPC `rom:autoLinkNetworkGames` in netplay.ts: fetch step 2's route, `linkNetworkGame` each candidate sequentially, skip failures/missing files silently, return `{ ok, linked }` (`{ ok: false, linked: 0 }` if unreachable). Add to preload.ts and emusync.d.ts.
  - Files: gui/electron/sync/netplay.ts, gui/electron/preload.ts, gui/renderer/src/emusync.d.ts
  - Reuses: `linkNetworkGame`
  - New: channel - no bulk link exists.
- [ ] 5. GameGrid: `handleRefreshLocations` calls `autoLinkNetworkGames()` first; `linked > 0` -> `onChanged()` and "N network game(s) linked." in `parts`. Mount-time `useEffect([])` calls it once, `onChanged()` when `linked > 0`, errors ignored.
  - Files: gui/renderer/src/components/GameGrid.tsx
  - Reuses: `parts`/`setBulkMsg`/`onChanged`
- [ ] 6. NetworkPlaySetup: `tryAutoImport` uses `window.emusync.rom.setupNetworkPlay(slug, mount)` instead of whole-mount scan + `roms[0]`; ok -> existing `onChanged(); onClose(); onPlay(...)`, else `setMode("manual")`.
  - Files: gui/renderer/src/components/NetworkPlaySetup.tsx
  - Reuses: `rom:setupNetworkPlay`
- [ ] 7. Tests in `src/tests/test_network_rom.py` (real SQLite, `client` fixture, two `X-Device-ID`s): (a) same share ID -> B gets one candidate with B's `mount_root` and A's `rom_rel_path`; (b) different share ID -> empty; (c) blank share ID either side -> empty; (d) B already has a config -> empty; (e) A never lists its own game; (f) two B console rows for the same console -> one candidate. Frontend: `npm run build` in src/gui for typecheck; no Electron test harness.
  - Files: src/tests/test_network_rom.py
- [ ] 8. Docs: CLAUDE.md network bullet (#660) and src/docs/ARCHITECTURE.md (REST route, IPC `rom:autoLinkNetworkGames`, netplay.ts, auto-link on Refresh locations and grid load).
  - Files: CLAUDE.md, src/docs/ARCHITECTURE.md

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): yes. New CLI subcommand: no. Config/data file change: no.

## Conflicts resolved
- CLAUDE.md, src/docs/ARCHITECTURE.md: both plans had a docs step; merged into step 8.
- Endpoint: frontend calls the backend's `GET /games/network-link-candidates`; ordered backend (1-2) before Electron (3-4) and renderer (5-6).

## Unresolved conflicts
- none

## Not in this plan
Enabling Play for non-local games. Sync-daemon/SSE-triggered linking. Server-side linking (server cannot verify the file on the client's mount).

## Log
- 2026-11-02 merge: 2 conflicts resolved, 0 unresolved
