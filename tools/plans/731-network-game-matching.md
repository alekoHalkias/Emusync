# Merged Plan: #731 Improve network game matching and prevent duplicate games

Source plans: tools/plans/731-network-game-matching-ui.md (fplan, commit dba21778), tools/plans/731-network-game-matching.md (bplan, commit 73855f52)
Branch: feature/731-network-game-matching
PR: #733
Status: implemented
Fix attempts: 0

## Goal
Store each device's ROM file size (schema v34) so games can be matched by casefolded filename + size: network games link silently on an exact share-ID + rel-path match and are proposed for confirmation on a filename + size match; moved local ROMs are proposed for relink; a new game reuses an existing one with the same ROM instead of creating a duplicate slug; CLI `run` finds a moved ROM for the current launch only.

## Matching rules (every step)
- Key: ROM basename casefolded (`/` and `\` both separators) + `rom_size`, same console.
- `rom_size = 0` (unknown or folder ROM) never matches; same name with a different size is not a match.
- File searches need exactly one hit; never "first ROM in mount".
- Fuzzy matches are never persisted without user confirmation (GUI) and never persisted by the CLI.

## Steps
### Backend
- [x] 1. Schema v34: `game_devices.rom_size INTEGER NOT NULL DEFAULT 0` in `_SCHEMA`, `_SCHEMA_VERSION = 34`, `if from_version < 34` `_try` ALTER. v34 verified free on all remote branches.
  - Files: src/server/store/schema.py
  - Reuses: `_try` / `_migrate` chain.
- [x] 2. Model + store round-trip: `GameDevice.rom_size: int = 0`; add to `set_game_device` INSERT, `get_game_device` SELECT, `games_overview` (`rom_size` key), `list_game_devices_for_device`.
  - Files: src/server/store/models.py, src/server/store/games.py
  - Reuses: existing inline column lists.
- [x] 3. Device API: `GameDeviceRequest.rom_size: Optional[int] = None` (None = keep stored value); `GET /games/{slug}/device` returns it. `sync_client.GameDeviceConfig.rom_size: Optional[int] = None`, read in `get_game_device`, sent only when not None.
  - Files: src/server/api/games.py, src/server/sync_client.py
  - Reuses: `set_game_device` route + `store.get_game_device` for the preserve read.
- [x] 4. `store.find_game_by_rom(console, filename, size) -> Optional[str]`: rows with `g.console = ?` and `gd.rom_size = ?` (> 0), basename of `rom_path` / `rom_rel_path` / `local_rom_path` compared casefolded in Python; oldest slug (lowest `games.rowid`) wins.
  - Files: src/server/store/games.py
  - New: method - no ROM-identity lookup exists; Python basename because SQLite has none for mixed separators.
- [x] 5. Dedup at creation: `GameRequest.rom_filename: str = ""`, `rom_size: int = 0`; `POST /games` returns the matched game with `"matched": true` when `find_game_by_rom` hits on the same console, else inserts as today with `"matched": false`. `sync_client.add_game(..., rom_filename="", rom_size=0)`. CLI `console import` passes basename + `os.path.getsize` (files only), sets `rom_size` on both `GameDeviceConfig` builds, prints "linked to existing <slug>" when matched.
  - Files: src/server/api/games.py, src/server/sync_client.py, src/cli/console.py
  - Reuses: existing route, client method, import loop.
- [x] 6. `cli/netrom.py:upload_to_network` sets `gd.rom_size` from the uploaded file.
  - Files: src/cli/netrom.py
  - Reuses: existing gd update block.
- [x] 7. Candidates: `network_link_candidates` exact query unchanged; rows gain `rom_size`, `filename` (basename of `rom_rel_path`), `match: "exact"`. Second query adds `match: "fuzzy"` rows: other devices' network rows with `rom_size > 0`, console where this device has a `device_network_folder`, no config on this device, slug not already exact; one row per slug (latest rowid), same `mount_root` field.
  - Files: src/server/store/games.py
  - Reuses: method, route, `mount_root` join.
  - New: second SELECT - one GROUP BY would mix exact/fuzzy bare columns.
- [x] 8. Python matcher `find_rom_by_name_size(roots, filename, size, console_key="")` in netrom.py over `detect._scan_rom_dir`.
  - Files: src/cli/netrom.py
  - Reuses: src/cli/detect.py:_scan_rom_dir.
  - New: thin name+size filter.
- [x] 9. CLI `run` fallback: no external `command` and the effective ROM is missing on disk -> search this device's console row folders (`device_network_folder`, `device_local_folder`, `device_game_folder`, `device_extra_folders`, via `client.get_device_consoles`) with step 8; on a hit resolve the launch command from a `dataclasses.replace(gd, rom_path=hit, launch_command=<old path replaced>)` copy (`_relocated_gd`), stderr note; stored config untouched.
  - Files: src/cli/run.py
  - Reuses: `_resolve_launch_command`, `get_device_consoles`, step 8.
  - New: `_relocated_gd(gd, console_row) -> gd | None` - run has no ROM search. Pure (caller fetches the console row) so it is testable without a server, like `_resolve_launch_command`.
### Frontend (after backend: depends on steps 2, 3, 5, 7)
- [x] 10. Types: `GameDeviceConfig.rom_size?: number`; `GameOverview.rom_size: number`; `GameRow.romSize` mapped in useGameList; `addGame(name, console?, rom?: { filename: string; size: number })` posts `rom_filename` / `rom_size` and returns `Game & { matched?: boolean }`.
  - Files: src/gui/renderer/src/api.ts, src/gui/renderer/src/components/game-list/types.ts, src/gui/renderer/src/components/game-list/useGameList.ts
  - Reuses: existing types, `_fetch`.
- [x] 11. `files:size` IPC (regular file size, else 0) + preload + emusync.d.ts.
  - Files: src/gui/electron/files.ts, src/gui/electron/preload.ts, src/gui/renderer/src/emusync.d.ts
  - Reuses: `files:exists` pattern.
  - New: channel - nothing exposes size (`files:get-file-hash` reads the whole file).
- [x] 12. TS matcher: export `scanRomDir`, add `findRomByNameSize(roots, filename, size, consoleKey?)` in scan.ts; IPC `rom:findByNameSize` + preload + d.ts.
  - Files: src/gui/electron/emulator/scan.ts, src/gui/electron/emulator/ipc.ts, preload.ts, emusync.d.ts
  - Reuses: scanRomDir (same walker semantics as Python `_scan_rom_dir`).
  - New: name+size filter + channel.
- [x] 13. netplay.ts: `linkNetworkGame` takes optional resolved `romPath` (rel path becomes this device's path under `mountRoot`) and PUTs `rom_size` from `statSync`. `rom:autoLinkNetworkGames` links exact rows as today; exact-but-missing and fuzzy rows go through `findRomByNameSize([mount_root], filename, rom_size)` and come back as `proposals: Array<{ slug, console, romPath, mountRoot }>` (additive). New `rom:confirmNetworkMatch(slug, romPath, mountRoot)` refetches `/games/{slug}/network-source` and calls `linkNetworkGame`. preload + d.ts.
  - Files: src/gui/electron/sync/netplay.ts, preload.ts, emusync.d.ts
  - Reuses: linkNetworkGame, network-source route, setupNetworkPlay body.
  - New: confirm channel - auto-link must not persist fuzzy hits.
- [x] 14. useBrokenRoms: `refresh` backfills `rom_size` for existing local ROMs with `romSize` 0; missing local ROMs with `romSize > 0` searched in the console folders via `rom:findByNameSize` and returned as relink proposals; `relink` sibling probe requires matching `files:size` when `romSize > 0`; `updateRom` sends `rom_size`.
  - Files: src/gui/renderer/src/components/game-list/useBrokenRoms.ts
  - Reuses: refresh loop, getDeviceConsoles, sourceFor folder list, updateRom.
- [x] 15. `MatchConfirmModal` (network-link and relink rows, checkboxes all checked, Link / Not now, inline per-row errors) and GameGrid wiring: load keeps proposals and shows "N possible game matches found. Review" in the status line; Refresh merges network + relink proposals, adds the count to its message, opens the modal (after LocalToNetworkModal if both apply). Session-declined slugs filtered.
  - Files: src/gui/renderer/src/components/MatchConfirmModal.tsx (new), src/gui/renderer/src/components/GameGrid.tsx
  - Reuses: LocalToNetworkModal structure/classes, Modal, `bulkMsg`, `handleRefreshLocations`.
  - New: component - LocalToNetworkModal's move/upload actions do not apply.
- [x] 16. Import dedup: `_runImport` sends `{ filename, size }` (via `files:size`) to `addGame` when `rom.linkedSlug` is unset; `matched` + already configured here (overview `is_local`) -> skip PUT, count as already imported; otherwise PUT with `rom_size`. Done phase shows "N linked to existing games". scanNewRoms unchanged.
  - Files: src/gui/renderer/src/components/console-import/useConsoleImport.ts (+ done-phase view)
  - Reuses: addGame, setGameDevice, gamesOverview.
### Verification and docs
- [x] 17. Tests (see Testing): new src/tests/test_network_matching.py; extend src/tests/test_network_autolink.py (fuzzy cases + update the exact key-set assertion); `make test-changed`. GUI: `make build-gui`, `make lint`, `tsc --noEmit` no new errors beyond the known list, manual script below.
- [x] 18. Docs: CLAUDE.md Rules (#731: matching key, v34 `rom_size`, POST /games dedup, fuzzy candidates, run fallback not persisted, files:size / rom:findByNameSize / rom:confirmNetworkMatch, MatchConfirmModal); src/docs/ARCHITECTURE.md (request/response fields, IPC table); src/docs/GOTCHAS.md (why fuzzy matches are never auto-persisted, rom_size 0 rows).

## Review fixes
- [x] 19. scan.ts: cache each root's scanRomDir result for a short TTL so one autoLink/refresh pass walks each folder once (findRomByNameSize reuses the cached list).
  - Files: src/gui/electron/emulator/scan.ts
  - Reuses: scanRomDir.
- [x] 20. netrom.py: find_rom_by_name_size skips roots that fail path_is_reachable (2s timeout) before scanning.
  - Files: src/cli/netrom.py
  - Reuses: path_is_reachable.

## Testing
- **Test Files**: src/tests/test_network_matching.py (new: schema, round-trip, POST /games dedup, Python matcher, run fallback); src/tests/test_network_autolink.py (extended: candidate `match` / fuzzy rows). Real SQLite, `client` fixture, `AUTH` + `_device_auth`, `tmp_path` files; no mocks.
- **Reuses**: conftest `client`, `AUTH`, `_device_auth`; test_network_rom.py `_add_game`, `_console_row`, `_set_share`; test_network_autolink.py `_setup`, `_network_game`, `_slugs`; migration pattern from test_switch_profile.py:test_v32_migration_adds_switch_profile_id; `SimpleNamespace` gd pattern from test_launch_command_token.py.
- **Test Cases**:
  - test_v33_migration_adds_rom_size: minimal old `game_devices` row, `_migrate(conn, 33)`, column = 0, data kept, user_version = `_SCHEMA_VERSION`.
  - test_rom_size_roundtrip_and_preserve: PUT with `rom_size=1234` -> GET returns it and overview row has it; second PUT without `rom_size` keeps 1234; PUT with `rom_size=0` sets 0.
  - test_add_game_matches_existing_rom: A imports "Pokemon Emerald" (GBA, `Pokemon Emerald (USA).gba`, 4096); POST /games "Emerald" with same filename + size returns the first slug, `matched: true`, and `GET /games` count unchanged.
  - test_add_game_no_match (parametrized): different size; different console; `rom_size=0`; no rom fields (old client) -> new slug, `matched: false`.
  - test_add_game_match_casefold_and_backslash: stored `C:\\Roms\\GBA\\POKEMON EMERALD (USA).GBA` matches `pokemon emerald (usa).gba`.
  - test_add_game_match_via_rel_path: network row matched through `rom_rel_path` basename.
  - test_find_rom_by_name_size (parametrized on tmp files written with `b"\0" * n`): unique hit -> path; same name, other size -> None; two hits in different subfolders -> None; size 0 -> None; missing root ignored.
  - test_relocated_gd_hit_rewrites_copy_only: missing `rom_path`, file of matching name + size under `device_local_folder` -> returned gd points at it, launch command rewritten (literal path and `%ROM%`), original gd unchanged.
  - test_relocated_gd_no_hit_returns_none: no file / ambiguous / `rom_size=0`.
  - test_network_autolink.py: test_exact_row_carries_match_fields (update key-set assertion to include `rom_size`, `filename`, `match`); test_fuzzy_listed_on_share_mismatch_with_size; test_fuzzy_listed_on_blank_share_with_size; test_fuzzy_not_listed_without_size (existing mismatch/blank tests keep passing because their seeds have size 0); test_fuzzy_not_listed_without_own_network_folder; test_fuzzy_not_listed_when_configured; test_exact_wins_over_fuzzy (one row per slug, `match == "exact"`).
- **Edge Cases**:
  - Old client PUT (no `rom_size`) never zeroes a stored size.
  - Two existing duplicates on the server: `find_game_by_rom` returns the oldest slug deterministically.
  - Folder ROMs (size 0) never match.
- **Integration Points**:
  - CLI `console import` -> `SyncClient.add_game` -> POST /games: covered by API tests plus a `live_server` test that `SyncClient.add_game(name, console, rom_filename, rom_size)` returns `matched` (real client, real server).
  - GUI (no JS runner, per testing guide): manual script with a dev server and two device configs (second via `EMUSYNC_CONFIG_DIR`): (1) exact share link still silent; (2) blank share + same filename/size file under the mount -> status line "1 possible game match", Review -> Link persists config, Not now leaves it unlinked; (3) rename a local ROM's folder -> Refresh proposes relink, Link fixes it; (4) import a renamed copy of an existing ROM -> no new game, "1 linked to existing games"; (5) `emusync run` with the ROM moved -> launches from found path, stderr note, `GET /games/{slug}/device` unchanged.

## Checklist
Schema bump: yes (v34). New IPC channel (+ emusync.d.ts): yes (files:size, rom:findByNameSize, rom:confirmNetworkMatch). New CLI subcommand: no. Config/data file change: no.

## Conflicts resolved
- POST /games body: fplan `{ filename, size }` mapped to bplan field names `rom_filename` / `rom_size` in api.ts (backend wins).
- network-link-candidates rows: fplan consumes bplan's `filename`, `rom_size`, `match` exactly; no shape change.
- rom_size on PUT: renderer spreads GET results (now carrying `rom_size`) and server preserves on None, so untouched callers (MoveLocalRomPanel, localToNetwork, etc.) need no change.
- Docs: CLAUDE.md / ARCHITECTURE.md edits from both plans folded into step 18.
- Ordering: backend steps 1-9 first; frontend 10-16 depend on 2, 3, 5, 7.
- Plan file: merged into the single `731-network-game-matching.md`; the `-ui` file removed so `require_plan.py` (takes the first `731-*.md` glob hit) sees one plan.

## Unresolved conflicts
- none

## Not in this plan
- Merging existing duplicates: #732.
- Persisting declined proposals across launches (display.json key if re-prompting annoys).
- CLI `rom_size` backfill (GUI Refresh backfills).
- GameConfig manual add dedup; content hashing.

## Log
- 2026-11-02 bplan: 11 steps written
- 2026-11-02 fplan: 10 steps written
- 2026-11-02 merge: 18 steps, 6 conflicts resolved, 0 unresolved
Step 7: updated test_network_autolink exact key-set assertion here (planned for step 17) to keep the suite green.
Step 9: _relocated_gd takes the device's console list + console name (not a single row) so the caller passes get_device_consoles output directly; added _rom_missing gate so the server is only asked when the ROM is actually missing.
Step 11-12: committed together (shared preload/d.ts edits); findRomByNameSize takes no consoleKey (dir ROMs have size 0 and never match, so the dir-pattern lookup is unneeded); the preload/d.ts entries for step 13's rom:confirmNetworkMatch were added here too.
Step 13: both matchers now return the path as seen under its root (dedupe still by realpath) so a symlinked mount relativizes cleanly.
Step 17: make test 724 passed / 3 skipped; make lint, make build-gui, tsc (no new errors) ok. GUI manual script NOT run (no display in this session) - left for the user, listed in the PR.
Step 20: path_is_reachable gained is_dir=True (it only probed files), reused by find_rom_by_name_size.
