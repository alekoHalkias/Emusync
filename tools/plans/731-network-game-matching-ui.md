# Plan: #731 Improve network game matching and prevent duplicate games (frontend)

Issue: #731
Branch: feature/731-network-game-matching
PR: none
Status: planned
Fix attempts: 0

## Goal
Send each ROM's size to the server, link exact network matches silently, and propose filename + size matches (network games and moved local ROMs) in one confirmation modal; import reuses an existing game when the server reports a ROM match.

## Design Alignment
- **Visual Pattern**: The confirmation prompt follows `LocalToNetworkModal` (Modal, `<h3>`, scrollable `<ul>`, one checkbox per row, `modal-actions` with `btn btn-ghost` "Not now" + `btn btn-primary` "Link"). Discovery on load uses the existing inline status line (`bulkMsg`) with a Review action, not an auto-opened modal.
- **Recommendations**: Proposal rows show game name and the found path so the user can judge the match. Declined proposals are kept for the session only (reappear next launch). Guide entry added under Modals for "match confirmation lists".

## Matching rules
Same as backend plan: casefolded basename + `rom_size`, same console; size 0 never matches; exactly one hit or no match.

## Steps
- [ ] 1. Types: `GameDeviceConfig.rom_size?: number`, `GameOverview.rom_size`, `GameRow.romSize` (mapped in useGameList), `addGame(name, console?, rom?: { filename: string; size: number })` returning `Game & { matched?: boolean }`; emusync.d.ts additions from steps 2-3.
  - Files: src/gui/renderer/src/api.ts, src/gui/renderer/src/components/game-list/types.ts, src/gui/renderer/src/components/game-list/useGameList.ts, src/gui/renderer/src/emusync.d.ts
  - Reuses: existing types and `_fetch("POST", "/games", ...)`.
- [ ] 2. `files:size` IPC: returns `statSync(p).size` for a regular file, else 0.
  - Files: src/gui/electron/files.ts, src/gui/electron/preload.ts, emusync.d.ts
  - Reuses: `files:exists` pattern.
  - New: channel - no existing IPC exposes file size (`files:get-file-hash` reads the whole file).
- [ ] 3. TS matcher: export `scanRomDir` and add `findRomByNameSize(roots, filename, size, consoleKey?)` in scan.ts (single hit or null; size 0 -> null). IPC `rom:findByNameSize(roots, filename, size, consoleKey?)`.
  - Files: src/gui/electron/emulator/scan.ts, src/gui/electron/emulator/ipc.ts, preload.ts, emusync.d.ts
  - Reuses: src/gui/electron/emulator/scan.ts:scanRomDir (depth-limited, ROM extensions, dir-ROM pattern) - same walker semantics as Python `detect._scan_rom_dir`.
  - New: thin name+size filter + channel; nothing existing filters by both.
- [ ] 4. netplay.ts: `linkNetworkGame` accepts an optional resolved `romPath` (rel path then = this device's path under `mountRoot`) and PUTs `rom_size` from `statSync`. `rom:autoLinkNetworkGames` links `match: "exact"` rows as today; when the exact ROM is missing, or the row is `match: "fuzzy"`, it calls `findRomByNameSize([mount_root], filename, rom_size)` and returns the hit as a proposal: `{ ok, linked, proposals: Array<{ slug, console, romPath, mountRoot }> }` (additive field). New IPC `rom:confirmNetworkMatch(slug, romPath, mountRoot)`: refetches `/games/{slug}/network-source` and calls `linkNetworkGame` with the given path.
  - Files: src/gui/electron/sync/netplay.ts, preload.ts, emusync.d.ts
  - Reuses: linkNetworkGame, `/games/{slug}/network-source`, the `rom:setupNetworkPlay` body.
  - New: confirm channel - auto-link must not persist fuzzy hits, so persisting needs its own call.
- [ ] 5. useBrokenRoms: (a) `refresh` backfills `rom_size` for local games whose file exists and `romSize` is 0 (one PUT each, best effort); (b) for each missing local ROM with `romSize > 0`, `rom:findByNameSize` over the console's folders (`device_game_folder`, extras, `device_local_folder`, `device_network_folder`) and return hits as relink proposals; (c) `relink` sibling probe also requires `files:size == other.romSize` when `romSize > 0`; (d) `updateRom` sends `rom_size` of the new path.
  - Files: src/gui/renderer/src/components/game-list/useBrokenRoms.ts
  - Reuses: existing refresh loop, `getDeviceConsoles`, `sourceFor` folder list, `updateRom`.
- [ ] 6. `MatchConfirmModal`: lists proposals (network link or relink) with checkboxes, all checked; Link applies `rom:confirmNetworkMatch` or `updateRom` per row, reports per-row errors inline, Close calls `onClose(changed)`.
  - Files: src/gui/renderer/src/components/MatchConfirmModal.tsx (new), src/gui/renderer/src/components/GameGrid.tsx
  - Reuses: LocalToNetworkModal structure and classes, Modal.
  - New: component - LocalToNetworkModal's actions (move/upload) do not apply; parameterizing it would mix two prompts.
- [ ] 7. GameGrid wiring: on load, keep `proposals` from auto-link and show "N possible game matches found. Review" in the status line (click opens the modal); Refresh locations merges network + relink proposals, adds the count to its message, and opens the modal when non-empty (after LocalToNetworkModal closes if both apply). Session-declined slugs filtered out.
  - Files: src/gui/renderer/src/components/GameGrid.tsx
  - Reuses: `bulkMsg` status line, `handleRefreshLocations`, existing modal state pattern.
- [ ] 8. Import dedup: `_runImport` gets `files:size` of the ROM and calls `addGame(displayName, consoleAbbr, { filename, size })` when `rom.linkedSlug` is unset; if the result is `matched` and that slug is already configured on this device (overview `is_local`), skip the PUT and count it as already imported; otherwise PUT with `rom_size`. Done phase shows "N linked to existing games" when non-zero. `scanNewRoms` unchanged (its count may include ROMs that will link on import; the wizard is the confirmation step).
  - Files: src/gui/renderer/src/components/console-import/useConsoleImport.ts (+ the done-phase view that renders importErrors)
  - Reuses: `addGame`, `setGameDevice`, `gamesOverview`, existing progress/result state.
- [ ] 9. Verify: `make build-gui`; `tsc --noEmit` shows no new errors beyond the known list (CLAUDE.md Ops); manual run against a dev server for: exact link, fuzzy proposal confirm/decline, moved ROM relink proposal, import of a renamed duplicate.
- [ ] 10. Docs: CLAUDE.md GUI rule (#731: files:size, rom:findByNameSize, rom:confirmNetworkMatch, MatchConfirmModal, proposals never auto-persisted); src/docs/ARCHITECTURE.md IPC table.

## Checklist
Schema bump: no (backend plan owns v34). New IPC channel (+ emusync.d.ts): yes (files:size, rom:findByNameSize, rom:confirmNetworkMatch). New CLI subcommand: no. Config/data file change: no.

## Not in this plan
- Persisting declined proposals across launches (add a `display.json` key if re-prompting annoys).
- GameConfig manual add dedup (no console/ROM known at that call site).
- Merging existing duplicates: #732.

## Log
- 2026-11-02 fplan: 10 steps written
