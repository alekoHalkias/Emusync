# Plan: #644 Redesign console import modal with optional network folder and share matching (frontend)

Issue: #644
Branch: feature/644-console-import-share-matching
PR: none
Status: planned
Fix attempts: 0

## Goal
Replace the ROM source toggle and tall top section of the console import results step with a compact Locations block (local folder + optional network folder with a share status chip) and auto-link games already on a matching share.

## Design Alignment
- **Visual Pattern**: Settings-form pattern from the design guide (#629): label + path + `btn btn-ghost` Choose per row, muted 12px helper text, list editor collapsed behind a disclosure. Status chip is a small inline span (muted for neutral, `var(--color-danger, #e5484d)` for mismatch, accent for match). Result of auto-link is the guide's inline status line, not a modal.
- **Recommendations**: Add a "Locations / status chip" entry to `.claude/frontend-design-guide.md`. Downstream code keeps working unchanged by deriving `romSource = networkRoot ? "network" : "local"` inside `useConsoleImport` (classifyByRoot, resolveImportPaths and postImport still read it). The network folder is the first element of `scanRoots` minus the local root, which resolveImportPaths already treats as the share root.

## Steps
- [ ] 1. IPC `files:ensure-share-marker(folder)`: read `<folder>/.emusync-share-id`; if missing try to write a new UUID (`crypto.randomUUID()`); returns `{ id: string | null, created: boolean }` (id null when absent and not writable). Expose in preload and `emusync.d.ts`.
  - Files: src/gui/electron/files.ts, src/gui/electron/preload.ts, src/gui/renderer/src/emusync.d.ts
  - Reuses: files.ts handler registration pattern (`files:exists`), Node fs already imported there
  - New: one handler - no existing marker or share-identity code
- [ ] 2. API wrappers: `getConsoleShares(consoleName)` for the backend `GET /consoles/{name}/shares`; `network_share_id?` on `DeviceConsole`; export a `getDeviceId()` accessor.
  - Files: src/gui/renderer/src/api.ts
  - Reuses: `_fetch`, `getDeviceConsoles`, `updateDeviceConsole`, module `_deviceId`
  - New: one wrapper and one accessor - `_deviceId` is private today
- [ ] 3. New hook `useNetworkShare(consoleLabel, networkRoot)` returning `{ status, shareId, peer }` where status is `none | checking | same | different | new | unverified`. On a root change: call step 1, then `getConsoleShares`; id matches a peer -> `same` (peer device name); id differs from all peers' ids while peers exist -> `different`; no peers -> `new`; id null -> `unverified` (falls back to no auto-link). Persists the share ID on this device's console row after link/import through `getDeviceConsoles` + `updateDeviceConsole` (existing fields passed back, `network_share_id` added).
  - Files: src/gui/renderer/src/components/console-import/useNetworkShare.ts (new)
  - Reuses: api.ts wrappers from step 2, `window.emusync.files`
  - New: separate file - useConsoleImport.ts is already 436 lines (limit ~300)
- [ ] 4. `useConsoleImport`: replace `romSource` state with `networkRoot` state (derived `romSource`); add `pickNetworkRoot`/`clearNetworkRoot`; seed networkRoot from the saved `import_rom_source === "network"` plus first saved folder, and persist `import_network_folder` next to the existing cfg keys; extract the per-ROM body of `_runImport` into `importOne(rom)` so it can be reused. After a `same` status, call `linkShareGames()`: rescan, take only entries with `linkedSlug`, run `importOne` on each (no new games), remove them from `roms`, and set an inline `linkedCount` shown as "N games linked".
  - Files: src/gui/renderer/src/components/console-import/useConsoleImport.ts
  - Reuses: scanRoms/dedupeAndLink (already sets `linkedSlug`), `resolveImportPaths`, `setGameDevice`, `classifyByRoot`
  - New: `importOne` is an extraction, not new logic; `linkShareGames` ~25 lines - nothing existing links without entering the importing phase
- [ ] 5. `ResultsStep`: replace the ROM source radio, local-copy row and ROM folders block with a Locations block: Local folder row (Choose, clear), Network folder row (Choose, clear, status chip, optional hint), then a "N folders scanned" disclosure that expands to the existing folder list and `+ Add folder`. Show the "N games linked" status line. Keep the network/local footer notes.
  - Files: src/gui/renderer/src/components/console-import/ResultsStep.tsx
  - Reuses: existing folder list markup, `vm.addExtraPath`, `vm.pickLocalRomRoot`, `.ci-check` and button classes
  - New: chip + disclosure markup (inline, no new component); if the file nears 300 lines, move the Locations block into `LocationsBlock.tsx`
- [ ] 6. Design guide entry for the Locations block and status chip.
  - Files: .claude/frontend-design-guide.md
- [ ] 7. Verification: the renderer has no JS test runner, so the share-status decision stays a small pure function `shareStatus(localId, peers)` in helpers.ts and is checked manually via `make dev-gui` (marker created on first folder; second device with same share shows Same share and links games; different share shows warning and links nothing; read-only folder shows Unverified). Server-side behavior is covered by the backend plan's integration tests.
- [ ] 8. Docs: ARCHITECTURE.md (IPC `files:ensure-share-marker`, hook list), CLAUDE.md GUI rule line (Locations block, marker file, `import_network_folder`).

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): yes (`files:ensure-share-marker`). New CLI subcommand: no. Config/data file change: yes (`import_network_folder` key beside `import_rom_source`; marker file `.emusync-share-id` on the share).

## Not in this plan
LibraryImport.tsx bulk-import source radio (library-level, #643 closed, left as is; it still seeds `import_rom_source`/`import_local_folder`, which step 4 keeps reading). Backend changes (see 644-console-import-share-matching.md).

## Log
