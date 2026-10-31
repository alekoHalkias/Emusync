# Merged Plan: #644 Redesign console import modal with optional network folder and share matching

Source plans: tools/plans/644-frontend-console-import.md, tools/plans/644-console-import-share-matching.md
Branch: feature/644-console-import-share-matching
PR: none
Status: planned
Fix attempts: 0

## Goal
Store a per-device-console network share ID, expose other devices' share IDs, and replace the ROM source toggle and tall top section of the console import results step with a Locations block that validates the share via a marker file and auto-links games already on a matching share.

## Steps
Backend first, then IPC and API client, then UI.
- [ ] 1. Add `consoles.network_share_id` (TEXT NOT NULL DEFAULT ''): model, `_SCHEMA`, migration `from_version < 30`, `_SCHEMA_VERSION = 30`, every consoles SQL literal.
  - Files: src/server/store/models.py, src/server/store/schema.py, src/server/store/consoles.py
  - Reuses: `_try` ALTER pattern, `_console_from_row`, existing set/get/list_console literals
  - New: none
- [ ] 2. Store method `list_console_shares(console_name, exclude_device_id)` returning `[{device_id, device_name, share_id}]` (other devices, non-empty IDs only).
  - Files: src/server/store/consoles.py
  - Reuses: join pattern of `get_network_source_for_game`
  - New: one query - no cross-device console lookup exists
- [ ] 3. API: `network_share_id` in `GET /devices/{id}/consoles`; `network_share_id: Optional[str] = None` on `ConsoleFoldersRequest` (None preserves); new `GET /consoles/{console_name}/shares` returning step 2's shape.
  - Files: src/server/api/devices.py
  - Reuses: `update_device_console` `exclude_none` loop, `_auth`, `_get_store`
  - New: one route - nothing lists other devices' consoles
- [ ] 4. Backend tests (real SQLite): v29 -> v30 migration keeps rows with '' default; PUT stores the ID and a PUT without it preserves it; `/consoles/{name}/shares` returns other devices only, skips blank IDs, mismatch case; 403 editing another device's console still holds.
  - Files: src/tests/test_integration.py
  - Reuses: `client` fixture, `AUTH` headers
- [ ] 5. IPC `files:ensure-share-marker(folder)` -> `{ id: string | null, created: boolean }` (reads or creates `.emusync-share-id`; id null when absent and unwritable); preload and `emusync.d.ts`.
  - Files: src/gui/electron/files.ts, src/gui/electron/preload.ts, src/gui/renderer/src/emusync.d.ts
  - Reuses: `files:exists` handler pattern
  - New: one handler - no marker code exists
- [ ] 6. API client: `getConsoleShares(consoleName)` (typed to step 3's shape), `network_share_id?` on `DeviceConsole`, exported `getDeviceId()`.
  - Files: src/gui/renderer/src/api.ts
  - Reuses: `_fetch`, `getDeviceConsoles`, `updateDeviceConsole`, `_deviceId`
  - New: one wrapper and one accessor
- [ ] 7. New hook `useNetworkShare(consoleLabel, networkRoot)` returning `{ status: none|checking|same|different|new|unverified, shareId, peer }`, using pure `shareStatus(localId, peers)` in helpers.ts; persists the share ID on this device's console row via get/update device console, passing existing fields back.
  - Files: src/gui/renderer/src/components/console-import/useNetworkShare.ts (new), helpers.ts
  - Reuses: step 5 and 6 APIs
  - New: separate file because useConsoleImport.ts exceeds 300 lines
- [ ] 8. `useConsoleImport`: replace `romSource` state with `networkRoot` (derived `romSource`), `pickNetworkRoot`/`clearNetworkRoot`, persist `import_network_folder` beside `import_rom_source`; extract `importOne(rom)` from `_runImport`; add `linkShareGames()` (rescan, import only entries with `linkedSlug`, drop them from `roms`, set `linkedCount`) triggered when status is `same`.
  - Files: src/gui/renderer/src/components/console-import/useConsoleImport.ts
  - Reuses: scanRoms/dedupeAndLink `linkedSlug`, `resolveImportPaths`, `setGameDevice`, `classifyByRoot`
  - New: `linkShareGames` (~25 lines) - nothing links without entering the importing phase
- [ ] 9. `ResultsStep`: Locations block (Local folder row, Network folder row with status chip, "N folders scanned" disclosure holding the folder list and `+ Add folder`), "N games linked" status line; split into `LocationsBlock.tsx` if the file nears 300 lines.
  - Files: src/gui/renderer/src/components/console-import/ResultsStep.tsx
  - Reuses: existing folder list markup, `vm.addExtraPath`, `vm.pickLocalRomRoot`, button classes
  - New: inline chip and disclosure
- [ ] 10. Manual verification via `make dev-gui` (renderer has no JS test runner): marker created on first folder; second device with same share shows Same share and links games; different share shows warning and links nothing; read-only folder shows Unverified.
- [ ] 11. Docs and guide: ARCHITECTURE.md (consoles column, `/consoles/{name}/shares`, IPC `files:ensure-share-marker`, hook list), CLAUDE.md (share identity via marker file and `network_share_id`, Locations block, `import_network_folder`), `.claude/frontend-design-guide.md` Locations/chip entry.

## Checklist
Schema bump: yes (29 -> 30). New IPC channel (+ emusync.d.ts): yes (`files:ensure-share-marker`). New CLI subcommand: no. Config/data file change: yes (`import_network_folder` key; `.emusync-share-id` marker on the share).

## Conflicts resolved
- No file is touched by both plans except docs: backend step 5 and frontend step 8 both edit ARCHITECTURE.md and CLAUDE.md; merged into step 11.
- API shape: frontend `getConsoleShares` typed to the backend's `[{device_id, device_name, share_id}]`; field `network_share_id` used by both.
- Ordering: backend (1-4) before IPC/client (5-6) before hook and UI (7-9).

## Unresolved conflicts
- none

## Not in this plan
LibraryImport.tsx bulk-import source radio (library-level; #643 closed). Server-side game linking. Dropping columns.

## Log
