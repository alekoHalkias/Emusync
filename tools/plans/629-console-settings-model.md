# Merged Plan: #629 Console settings model: consolidate ROM/local-copy folders, real emulator dropdown, extra ROM folder management

Source plans: tools/plans/629-console-settings-model.md (bplan, steps 1-5 backend), tools/plans/629-console-settings-model-ui.md (fplan, steps 6-12 frontend)
Branch: feature/629-console-settings-model
PR: none
Status: implementing
Fix attempts: 0

## Goal
Add a `device_extra_folders` list to each console row (storage, upsert routing, REST) and rewrite ConsoleFoldersModal on top of it: one block per console, a real emulator dropdown, a conditional copy-destination field, and an Other ROM folders section.

## Steps
- [x] 1. Schema + model: `consoles.device_extra_folders TEXT NOT NULL DEFAULT '[]'`, `_SCHEMA_VERSION` 28 -> 29, `if from_version < 29` ALTER block; `Console.device_extra_folders: list[str]` (default_factory list).
  - Files: src/server/store/schema.py, src/server/store/models.py
  - Reuses: schema.py `_try(conn, "ALTER TABLE consoles ADD COLUMN ...")` pattern at the < 27 block; keep trailing user_version stamp
  - New: none
- [x] 2. Store boundary: add the column to `set_console` / `get_console` / `list_consoles` SQL; serialize with `json.dumps`, parse with `json.loads` into the dataclass (small private `_console_from_row` used by get and list, so `Console(**dict(row))` is not duplicated with JSON handling).
  - Files: src/server/store/consoles.py
  - Reuses: console_defs.py json.dumps/json.loads usage
  - New: `_console_from_row` - two call sites now need the same JSON parse, one helper beats two copies
- [x] 3. Upsert routing: in `upsert_console_for_game`, select the row by `console_name` (prefer the row whose `device_game_folder == game_folder`, else the first row for that console). If a non-blank `game_folder` differs from that row's folder and is not already in `device_extra_folders` (and not another legacy row's folder), append it to extras instead of creating a row. Blank `game_folder` never creates a row when the console already has one. A `game_folder` equal to or inside the row's `device_network_folder` is never appended (a network-sourced game must not turn its NAS mount into a local extra, which `sourceFor` would then misclassify as local). Fill-only-blank for save/state/emulator stays as is. No row for the console: create as today.
  - Files: src/server/store/consoles.py
  - Reuses: existing `existing_consoles` lookup and fill-only-blank block
  - New: none
- [x] 4. REST: `GET /devices/{id}/consoles` returns `device_extra_folders`; `ConsoleFoldersRequest.device_extra_folders: Optional[list[str]] = None`; PUT skips None fields, normalizes the list (strip, drop blanks, dedupe, drop the primary `device_game_folder`). Docstring updated ("replaces all six folder fields; extras preserved when omitted").
  - Files: src/server/api/devices.py
  - Reuses: the `model_dump()` setattr loop (add `exclude_none=True`)
  - New: none
- [ ] 5. Tests (real SQLite): see step list below.
  - Files: src/tests/test_devices.py (new cases near the #539 tests), src/tests/test_network_rom.py (migration case beside `test_v9_to_v10_migration`)
  - Cases: (a) GET returns `device_extra_folders == []` for a fresh console; (b) PUT sets extras, GET round-trips them, normalization drops blanks/dupes/primary folder; (c) PUT omitting the field preserves existing extras (regression for old clients); (d) second `PUT /games/{slug}/device` with a rom in a different folder for the same console adds an extra and leaves one console row; (e) same-folder repeat does not duplicate extras; save-only game (blank folder) adds no row; (f) hand-chosen `device_emulator` survives a later game config save with a different save dir (AC 4); (g) legacy two-row console still lists both rows and a new game in either row's folder creates no extras; (h) v28 DB migrates and gains the column with `[]`; (i) a network-sourced game whose `rom_folder_path` is inside the console's `device_network_folder` adds no extra; PUT 403/404 paths already covered.
- [ ] 6. API types: `DeviceConsole` gains `device_extra_folders?: string[]`; `updateDeviceConsole` already takes the Omit type so the payload carries it. Doc comment updated.
  - Files: src/gui/renderer/src/api.ts
  - Reuses: existing `DeviceConsole` / `updateDeviceConsole`
  - New: none
- [ ] 7. Refresh classification: `sourceFor()` adds each `device_extra_folders` entry as a `local` candidate (longest-prefix logic unchanged), so #616 broken-ROM badge and #618 local/network tagging treat extras as local locations.
  - Files: src/gui/renderer/src/components/game-list/useBrokenRoms.ts
  - Reuses: `sourceFor` candidates array and `.filter(inside)`
  - New: none
- [ ] 8. Modal body rewrite, group and fields: pick the primary row for the console (the row whose `device_game_folder` is non-blank, first wins; matches backend upsert); render one `config-form` with ROM folder, Save folder, States folder, Emulator, Network (NAS) folder. Copy field ("Copy network ROMs to") renders only when the network folder is non-blank, placeholder shows the ROM folder; on Save, blank copy folder with a network folder set is written as the ROM folder so `device_local_folder` consumers (Move/Network panels, cli/rom.py) see the effective value. Single PUT with all fields. Keep the shared-memcard note and the empty state.
  - Files: src/gui/renderer/src/components/ConsoleFoldersModal.tsx
  - Reuses: existing `edit`/`browse`/`save` handlers, `updateDeviceConsole`, `usesSharedSaveLayout`; FIELDS array trimmed to the plain-text pickers
  - New: none (same component; no new file)
- [ ] 9. Emulator dropdown: on open call `window.emusync.emulator.detect(consoleKey)`; options = detected `label`s plus a blank "Not set" entry plus the currently stored value if it is not among them (legacy derived or custom text). Stored value = the label string. Label-only: no launch_command rewrite.
  - Files: src/gui/renderer/src/components/ConsoleFoldersModal.tsx
  - Reuses: `emulator:detect` IPC and `DetectedEmulatorOption.label` (already typed in emusync.d.ts); ConsoleStep select markup
  - New: none; no IPC channel added
- [ ] 10. Other ROM folders section (bottom): list `device_extra_folders` each with Remove, plus legacy rows' `device_game_folder` (other rows for this console) shown read-only with a one-line note; `Add folder` opens `dialog.openFolder`, ignores blanks and duplicates, and the section saves with the main Save button. Remove edits local state only.
  - Files: src/gui/renderer/src/components/ConsoleFoldersModal.tsx
  - Reuses: `browse` pattern, `window.emusync.dialog.openFolder`
  - New: none
- [ ] 11. Retire the stale helper text ("Changing the ROM folder starts a new entry...") since upsert now routes differing folders into extras, and replace with one line about Other ROM folders.
  - Files: src/gui/renderer/src/components/ConsoleFoldersModal.tsx
- [ ] 12. Verification: no JS test runner exists in the repo, so run `make lint` (tsc node+web), then drive the modal with the `run` skill: open a console with a network folder, an unset emulator, one extra folder; Save; reopen; confirm persistence and that Refresh locations does not flag a ROM under an extra folder as outside the console folder.
- [ ] 13. Docs (merged): src/docs/ARCHITECTURE.md (consoles data model: new column, upsert routing; modal behavior if listed), CLAUDE.md (upsert rule line for extras; GUI rule line for ConsoleFoldersModal: one block per console, extras, label-only emulator, #629), .claude/frontend-design-guide.md (Settings forms entry).
  - Files: src/docs/ARCHITECTURE.md, CLAUDE.md, .claude/frontend-design-guide.md
  - Reuses: n/a; the two plans' docs steps (backend 6, frontend 8) touched the same CLAUDE.md and ARCHITECTURE.md, so they are one step

## Testing
- **Test File**: src/tests/test_devices.py (API + upsert cases, placed under a new "console extra folders (#629)" section after the #539 tests, reusing `_seed_console`, `AUTH`, `DEVICE_ID`, `_device_auth`); src/tests/test_network_rom.py (migration case beside `test_v9_to_v10_migration`, network-folder case beside the existing console-folder tests). No new files, no new fixtures.
- **Test Cases**:
  - extras default: `GET /devices/{id}/consoles` after `_seed_console` returns `device_extra_folders == []`.
  - extras round-trip: PUT with `["/roms/snes2", "/roms/snes3"]`, GET returns them in order.
  - normalization: PUT with blanks, duplicates, whitespace, and the primary `device_game_folder` returns a cleaned list.
  - preserve on omit (regression): PUT body without `device_extra_folders` keeps existing extras; PUT with `[]` clears them.
  - upsert routing: second `PUT /games/{slug}/device` for the same console with a ROM in a different folder yields one console row and the folder in extras.
  - emulator survives (AC 4): PUT sets `device_emulator = "custom"`, then a game config save with a different save dir leaves it unchanged (extends the existing #539 regression to the new routing path).
  - migration: minimal v28-shaped `consoles` table, `schema._migrate(conn, from_version=28)`, column exists with `'[]'`, existing row kept, `user_version` stamped.
- **Edge Cases**:
  - same-folder repeat adds no duplicate extra; second row never created.
  - save-only game (blank game folder) on a console that already has a row adds no row and no extra.
  - legacy two-row console (two rows with different `device_game_folder`): both still listed; a game in either folder creates no extra; a game in a third folder lands in the extras of the row chosen by `console_name` first-match.
  - network-sourced game under `device_network_folder` adds no extra (misclassification guard).
  - first-ever game for a console with no row still creates the row exactly as before (no extras).
  - PUT 403/404 already covered by `test_update_device_console_errors`; the new field does not change them.
- **Integration Points**:
  - `PUT /games/{slug}/device` -> `upsert_console_for_game` -> `GET /devices/{id}/consoles` is the full path every case drives through the real FastAPI app and SQLite.
  - Existing `test_game_config_save_does_not_overwrite_edited_console_folders` and `test_network_import_populates_and_preserves_console_folders` must still pass unchanged (they exercise the changed upsert).
  - Frontend: no JS test runner; covered by `make lint` (tsc) and the manual check in step 12. `make test-changed` runs the two Python files.

## Checklist
Schema bump: yes (28 -> 29). New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no (DB column only).

## Conflicts resolved
- CLAUDE.md and src/docs/ARCHITECTURE.md: both plans had a docs step; merged into step 13.
- API field: backend PUT field is `Optional[list[str]] = None` (None = preserve); frontend always sends the full list, so it replaces. Compatible, no change.
- Ordering: backend steps 1-5 (schema, store, upsert, REST, tests) precede frontend steps 6-12, since the modal reads `device_extra_folders` from GET.
- Step 5 vs frontend: the backend normalizes extras (strip, dedupe, drop primary), so the modal need not; it only ignores blank and duplicate adds for UX.

## Unresolved conflicts
none

## Not in this plan
- `sync_client.GameDeviceConfig` carrying extras to other devices; CLI `console list` extras column.
- Deleting legacy multi-row consoles or adding a DELETE route.
- Rewriting per-game launch commands when the emulator changes.
- GameConfig.tsx, MoveLocalRomPanel, NetworkRomPanel, localToNetwork (read-through only).

## Log
Step 3: also skips a folder nested inside an already-known folder (primary, legacy rows, network), and fills a blank primary folder instead of adding an extra, so save-only-then-ROM games do not leave the primary blank.
