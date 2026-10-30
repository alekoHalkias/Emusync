# Plan: #629 Console settings model: consolidate ROM/local-copy folders, real emulator dropdown, extra ROM folder management

Issue: #629
Branch: feature/629-console-settings-model
PR: none
Status: planned
Fix attempts: 0

## Goal
Add a `device_extra_folders` list to each console row (storage, upsert routing, REST), so the GUI can show one block per console with an extras section and a chosen emulator.

## Design Alignment
- **Backend Pattern**: Additive JSON-TEXT column (`console_defs.dirs_json` precedent) with `json.dumps`/`json.loads` at the Store boundary; PUT field is `Optional[...] = None` meaning "preserve" so pre-#629 clients cannot blank extras; `upsert_console_for_game` stays the single inference point for API and CLI.
- **Recommendations**: Guide gains one line on Optional-means-preserve for list fields in PUT bodies. `device_emulator` needs no backend change: `upsert_console_for_game` is already fill-only-blank and PUT is the only writer of a chosen value; a regression test pins this.

## Steps
- [ ] 1. Schema + model: `consoles.device_extra_folders TEXT NOT NULL DEFAULT '[]'`, `_SCHEMA_VERSION` 28 -> 29, `if from_version < 29` ALTER block; `Console.device_extra_folders: list[str]` (default_factory list).
  - Files: src/server/store/schema.py, src/server/store/models.py
  - Reuses: schema.py `_try(conn, "ALTER TABLE consoles ADD COLUMN ...")` pattern at the < 27 block; keep trailing user_version stamp
  - New: none
- [ ] 2. Store boundary: add the column to `set_console` / `get_console` / `list_consoles` SQL; serialize with `json.dumps`, parse with `json.loads` into the dataclass (small private `_console_from_row` used by get and list, so `Console(**dict(row))` is not duplicated with JSON handling).
  - Files: src/server/store/consoles.py
  - Reuses: console_defs.py json.dumps/json.loads usage
  - New: `_console_from_row` - two call sites now need the same JSON parse, one helper beats two copies
- [ ] 3. Upsert routing: in `upsert_console_for_game`, select the row by `console_name` (prefer the row whose `device_game_folder == game_folder`, else the first row for that console). If a non-blank `game_folder` differs from that row's folder and is not already in `device_extra_folders` (and not another legacy row's folder), append it to extras instead of creating a row. Blank `game_folder` never creates a row when the console already has one. Fill-only-blank for save/state/emulator stays as is. No row for the console: create as today.
  - Files: src/server/store/consoles.py
  - Reuses: existing `existing_consoles` lookup and fill-only-blank block
  - New: none
- [ ] 4. REST: `GET /devices/{id}/consoles` returns `device_extra_folders`; `ConsoleFoldersRequest.device_extra_folders: Optional[list[str]] = None`; PUT skips None fields, normalizes the list (strip, drop blanks, dedupe, drop the primary `device_game_folder`). Docstring updated ("replaces all six folder fields; extras preserved when omitted").
  - Files: src/server/api/devices.py
  - Reuses: the `model_dump()` setattr loop (add `exclude_none=True`)
  - New: none
- [ ] 5. Tests (real SQLite): see step list below.
  - Files: src/tests/test_devices.py (new cases near the #539 tests), src/tests/test_network_rom.py (migration case beside `test_v9_to_v10_migration`)
  - Cases: (a) GET returns `device_extra_folders == []` for a fresh console; (b) PUT sets extras, GET round-trips them, normalization drops blanks/dupes/primary folder; (c) PUT omitting the field preserves existing extras (regression for old clients); (d) second `PUT /games/{slug}/device` with a rom in a different folder for the same console adds an extra and leaves one console row; (e) same-folder repeat does not duplicate extras; save-only game (blank folder) adds no row; (f) hand-chosen `device_emulator` survives a later game config save with a different save dir (AC 4); (g) legacy two-row console still lists both rows and a new game in either row's folder creates no extras; (h) v28 DB migrates and gains the column with `[]`; PUT 403/404 paths already covered.
- [ ] 6. Docs: src/docs/ARCHITECTURE.md (consoles data model: new column, upsert routing), CLAUDE.md "Saves / sync" rule line for `upsert_console_for_game` (also folds extras, #629); GOTCHAS only if a surprise appears.
  - Files: src/docs/ARCHITECTURE.md, CLAUDE.md

## Checklist
Schema bump: yes (28 -> 29). New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no (DB column only).

## Not in this plan
- GUI (modal rewrite, emulator dropdown, `DeviceConsole` type, `useBrokenRoms.sourceFor`): fplan.
- `sync_client.GameDeviceConfig` carrying extras to other devices.
- CLI `console list` extras column.
- Rewriting or deleting legacy multi-row consoles.

## Log
