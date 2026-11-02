# Plan: #731 Improve network game matching and prevent duplicate games

Issue: #731
Branch: feature/731-network-game-matching
PR: none
Status: planned
Fix attempts: 0

## Goal
Store each device's ROM file size so network games can be matched by filename + size when the share ID or rel path fails, and so a new game reuses an existing one with the same ROM instead of creating a duplicate slug.

## Design Alignment
- **Backend Pattern**: Additive column (schema v34) and defaulted request fields, per the guide. Dedup lives in the single game-creation route (`POST /games`), the one choke point every client (GUI import, CLI import, GameConfig) already calls. Fuzzy network candidates extend the existing `/games/network-link-candidates` route rather than adding one. CLI file search reuses `detect._scan_rom_dir`.
- **Recommendations**: `rom_size` on the device PUT is `Optional[int] = None` meaning preserve the stored value, so older clients (which PUT the whole field set without it) cannot zero it. Added to the guide's API conventions as the scalar form of the existing preserve-on-None rule.

## Matching rules (shared by every step)
- Match key: ROM basename (casefold, `\` and `/` both separators) + `rom_size`, same console.
- `rom_size = 0` (unknown, or a folder ROM) never matches.
- Same filename with a different size is not a match. Never "first ROM in mount".
- Exactly one hit required where a file search is involved; more than one = no match.

## Steps
- [ ] 1. Schema v34: `game_devices.rom_size INTEGER NOT NULL DEFAULT 0`. Observable: fresh DB and a v33 DB both have the column, `user_version = 34`.
  - Files: src/server/store/schema.py
  - Reuses: `_try` ALTER pattern, existing `from_version < N` chain (v34 verified free on all remote branches).
  - New: nothing beyond the column.
- [ ] 2. Model + store round-trip: add `rom_size: int = 0` to `GameDevice`; include it in `set_game_device` INSERT, `get_game_device` SELECT, `games_overview` (dict key `rom_size`), `list_game_devices_for_device`.
  - Files: src/server/store/models.py, src/server/store/games.py
  - Reuses: existing inline column lists (guide: edit every literal for the table).
- [ ] 3. Device API: `GameDeviceRequest.rom_size: Optional[int] = None`; `set_game_device` route keeps the stored value when None; `GET /games/{slug}/device` returns `rom_size`. `sync_client.GameDeviceConfig.rom_size: Optional[int] = None`, read in `get_game_device`, sent in `set_game_device` only when not None.
  - Files: src/server/api/games.py, src/server/sync_client.py
  - Reuses: existing route + `store.get_game_device` for the preserve read; guide preserve-on-None rule.
- [ ] 4. Store lookup `find_game_by_rom(console, filename, size) -> Optional[str]`: rows with `g.console = ?` and `gd.rom_size = ? > 0`, compared in Python on casefolded basename of `rom_path`, `rom_rel_path`, `local_rom_path`; returns the oldest matching slug (lowest `games.rowid`).
  - Files: src/server/store/games.py
  - Reuses: nothing does a ROM-identity lookup today (`get_network_source_for_game` is per-slug).
  - New: one method; basename compare in Python because SQLite has no portable basename for mixed separators.
- [ ] 5. Dedup at creation: `GameRequest` gains `rom_filename: str = ""`, `rom_size: int = 0`. `POST /games`: when both set and `find_game_by_rom` finds a slug on the same console, return that game with `"matched": true` instead of inserting; otherwise unchanged (`"matched": false`). `sync_client.add_game(..., rom_filename="", rom_size=0)`. CLI `console import` passes basename + `os.path.getsize` (files only) and sets `rom_size` on the `GameDeviceConfig` (local and `_build_network_game_device`); prints "linked to existing <slug>" when matched.
  - Files: src/server/api/games.py, src/server/sync_client.py, src/cli/console.py
  - Reuses: existing `add_game` route/client/CLI loop; `client.add_game` result slug already drives the PUT.
- [ ] 6. `cli/netrom.py:upload_to_network` sets `gd.rom_size` from the uploaded file so network masters carry it.
  - Files: src/cli/netrom.py
  - Reuses: existing `gd` update block before `client.set_game_device`.
- [ ] 7. Fuzzy network candidates: `network_link_candidates` keeps its exact query untouched, each row gains `rom_size`, `filename` (basename of `rom_rel_path`) and `match: "exact"`. A second query adds `match: "fuzzy"` rows: other devices' `rom_source='network'` rows with `rom_size > 0`, game console where this device has a `device_network_folder`, no config on this device, slug not already exact. One row per slug (latest rowid). Route unchanged.
  - Files: src/server/store/games.py
  - Reuses: existing method, route, and `mount_root` join.
  - New: second SELECT - folding it into the first would make GROUP BY mix exact/fuzzy rows.
- [ ] 8. Python matcher `find_rom_by_name_size(roots, filename, size, console_key="") -> Optional[str]`: runs `detect._scan_rom_dir` over each existing root, keeps casefolded basename + `os.path.getsize` equal, returns the single hit or None (0 or >1 hits, or size 0).
  - Files: src/cli/netrom.py
  - Reuses: src/cli/detect.py:_scan_rom_dir (depth-limited, ROM-extension aware).
  - New: thin filter over it; nothing existing filters by name + size.
- [ ] 9. CLI `run` fallback: in `run_game`, when no external `command` was given and the ROM `_resolve_launch_command` would use does not exist on disk, look up this device's console row (`client.get_device_consoles`, matched on the game's console like `upload_to_network`), search `device_network_folder`, `device_local_folder`, `device_game_folder` and `device_extra_folders` with `find_rom_by_name_size(..., gd.rom_size)`. On a hit, resolve the launch command from a `dataclasses.replace(gd, rom_path=hit, launch_command=<old path replaced>)` copy and print a stderr note naming the path; the stored config is not changed (fuzzy matches are only persisted after GUI confirmation). No hit: existing behavior.
  - Files: src/cli/run.py
  - Reuses: `_resolve_launch_command`, `client.get_device_consoles`, step 8 matcher.
  - New: small `_relocated_gd` helper in run.py - run has no ROM search today.
- [ ] 10. Tests: src/tests/test_network_matching.py, real SQLite, no mocks. v33->v34 migration; rom_size round-trip and None-preserve on PUT; POST /games match / size mismatch / other console / size 0 / casefold + backslash basename; candidates exact unchanged + fuzzy present, size-0 and already-configured excluded, exact wins; `find_rom_by_name_size` unique / ambiguous / size mismatch on tmp files; `_relocated_gd` hit leaves stored config unchanged.
- [ ] 11. Docs: CLAUDE.md Rules line (#731 matching key, `rom_size` v34, dedup in POST /games, fuzzy candidates, run fallback not persisted); src/docs/ARCHITECTURE.md for the new request/response fields; GOTCHAS entry on why fuzzy matches are never auto-persisted.

## Checklist
Schema bump: yes (v34). New IPC channel (+ emusync.d.ts): no (backend side). New CLI subcommand: no. Config/data file change: no.

## Not in this plan
- Merging existing duplicates: #732.
- Backfilling `rom_size` for existing rows: GUI Refresh locations (frontend plan) sends it on re-link/refresh; CLI does not backfill.
- Content hashing.

## Log
- 2026-11-02 bplan: 11 steps written
