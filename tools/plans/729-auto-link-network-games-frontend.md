# Plan: #729 Auto-link network-drive games on devices sharing the same network share (frontend)

Issue: #729
Branch: feature/729-auto-link-network-games
PR: none
Status: planned
Fix attempts: 0

## Goal
Network-drive games on a share this device has with the same share ID become linked and playable here automatically, using the existing (currently uncalled) `rom:setupNetworkPlay` logic.

## Design Alignment
- **Visual Pattern**: No new UI. The Refresh locations status line (`setBulkMsg`) gains a "N network game(s) linked." part, matching its existing "N ROM sources corrected" phrasing.
- **Recommendations**: Move the network-play code out of `sync/rom.ts` (552 lines, over the ~300 limit) into its own module rather than growing it.

## Steps
- [ ] 1. Move `rom:setupNetworkPlay`, `tailSegments` and `consoleSaveStateFolders` from `gui/electron/sync/rom.ts` into new `gui/electron/sync/netplay.ts`. Split the handler body into `linkNetworkGame(slug, src, mountRoot)` (src = the network-source fields) that does the rel-path safety check, `existsSync`, path rewrite and `PUT /games/{slug}/device`. `rom:setupNetworkPlay` keeps its signature: fetch `/games/{slug}/network-source`, then call `linkNetworkGame`. Export `registerNetPlayIpc()` and call it from `gui/electron/sync.ts` beside `registerRomIpc()`.
  - Files: gui/electron/sync/rom.ts, gui/electron/sync/netplay.ts, gui/electron/sync.ts
  - Reuses: the existing handler body verbatim, `loadServerCfg`
  - New: netplay.ts - rom.ts is already 552 lines; the function split is needed so step 2 can reuse it without a second fetch per game.
- [ ] 2. IPC `rom:autoLinkNetworkGames` in netplay.ts: `GET /games/network-link-candidates` (backend B2), call `linkNetworkGame(c.slug, c, c.mount_root)` for each, sequentially, counting `ok`; a missing file or failure is skipped silently. Returns `{ ok, linked }`; server unreachable returns `{ ok: false, linked: 0 }`. Add to preload.ts (`rom.autoLinkNetworkGames`) and emusync.d.ts.
  - Files: gui/electron/sync/netplay.ts, gui/electron/preload.ts, gui/renderer/src/emusync.d.ts
  - Reuses: `linkNetworkGame` (step 1), fetch + `AbortSignal.timeout` pattern of the same file
  - New: IPC channel - no channel links in bulk.
- [ ] 3. GameGrid: in `handleRefreshLocations`, call `window.emusync.rom.autoLinkNetworkGames()` first; if `linked > 0`, call `onChanged()` and add "N network game(s) linked." to `parts`. Add a mount-time `useEffect` (deps `[]`) that calls it once and `onChanged()` when `linked > 0`, errors ignored.
  - Files: gui/renderer/src/components/GameGrid.tsx
  - Reuses: existing `parts`/`setBulkMsg` and `onChanged`
- [ ] 4. NetworkPlaySetup: replace `tryAutoImport`'s whole-mount `emulator.scan` + `scanResult.roms[0]` with `window.emusync.rom.setupNetworkPlay(slug, mount)`; on `ok` keep the existing `onChanged(); onClose(); onPlay(...)`, else `setMode("manual")`. Drop the now-unused `key` parameter use.
  - Files: gui/renderer/src/components/NetworkPlaySetup.tsx
  - Reuses: `rom:setupNetworkPlay`
- [ ] 5. Tests: no renderer/Electron test harness exists in the repo; the matching logic is in the backend query (backend B3). Verify with `npm run build` in src/gui (typecheck of the new channel) and a manual two-device check noted in the PR.
- [ ] 6. Docs: CLAUDE.md network bullet (#660) and src/docs/ARCHITECTURE.md IPC list: `rom:autoLinkNetworkGames`, netplay.ts, and that Refresh locations and grid load auto-link matching-share games.
  - Files: CLAUDE.md, src/docs/ARCHITECTURE.md

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): yes. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
Enabling Play for non-local games (unneeded once games auto-link). Sync-daemon/SSE-triggered linking (grid load + Refresh cover it; add if games added while the grid is open need it).

## Log
- 2026-11-02 fplan: 6 steps written
