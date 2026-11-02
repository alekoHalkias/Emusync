# Plan: #727 Place Switch saves into each device's own Eden profile

Issue: #727
Branch: feature/727-switch-device-profile
PR: none
Status: planned
Fix attempts: 0

## Goal
Every device keeps one Eden profile on its Switch console row, and Switch saves are matched, seeded, pulled and detected only inside `<nand root>/<that profile>/<title id>`.

## Design Alignment
- **Backend Pattern**: Per-device console column with Optional preserve-if-None on the existing `PUT /devices/{id}/consoles/{console_id}`, exactly like `network_share_id` (#644). Schema v33 per the evolution rules (main and server PC are at 32). All Switch save placement already funnels through `run_switch._switch_profile_dirs()`; restricting that one function fixes find/seed/resolve/ensure/pull for every caller.
- **Recommendations**: Profile auto-detected from Eden's `profiles.dat` (byte-reversed 16-byte UUID = folder name; verified on Arch: UUID bytes b6ff0f84...97b94db6 -> folder B64DB997096B19C19A95F548840FFFB6). Stored value wins over detection so a wrong pick can be fixed by editing the row.

## Steps
- [ ] 1. Store + API: `consoles.switch_profile_id TEXT NOT NULL DEFAULT ''` (`_SCHEMA`, `_SCHEMA_VERSION = 33`, `if from_version < 33` ALTER); `Console.switch_profile_id`; add to `set_console`/`get_console`/`list_consoles` column lists; `GET /devices/{id}/consoles` returns it; `ConsoleFoldersRequest.switch_profile_id: Optional[str] = None`.
  - Files: src/server/store/schema.py, src/server/store/models.py, src/server/store/consoles.py, src/server/api/devices.py
  - Reuses: network_share_id column/field pattern end to end
  - New: none beyond the column
- [ ] 2. Client: `SyncClient.update_device_console(device_id, console: dict)` PUTs the full row (the route replaces all folder fields, so the caller sends back what it read plus `switch_profile_id`).
  - Files: src/server/sync_client.py
  - Reuses: `get_device_consoles` request style
  - New: one method - no client wrapper for this PUT exists (the GUI calls it from api.ts).
- [ ] 3. Profile detection and restriction in `run_switch.py`: `_eden_profile_folders(save_root)` parses `<eden root>/nand/system/save/8000000000000010/su/avators/profiles.dat` (0x10 header, 0xC8-byte entries, first 16 bytes = UUID, skip all-zero, folder = reversed bytes as upper hex). Module-level `_device_profile` set via `_set_switch_profile(p)`. `_switch_profile_dirs()` returns `root/<_device_profile>` (created if missing) when set; else the profiles.dat folders that exist; else today's non-`.bak` scan.
  - Files: src/cli/run_switch.py
  - Reuses: `_SWITCH_NAND_ROOTS`, existing `_switch_profile_dirs` call sites unchanged
  - New: profiles.dat parser - no existing reader. Module-level profile: ponytail, avoids threading a param through five functions; a param if more callers appear.
- [ ] 4. `_resolve_switch_profile(client, cfg) -> str` in run_switch.py: read this device's Switch console row (`shortform_name` or `console_name` == "Switch"); use its `switch_profile_id`, else the first detected profiles.dat folder and store it on the row via `update_device_console` (fill-only-blank, best effort); call `_set_switch_profile`. Call it in `run_game` for Switch, and in `game.py` `ensure-switch-save-folder` / `pull-switch-save`.
  - Files: src/cli/run_switch.py, src/cli/run.py, src/cli/game.py
  - Reuses: `client.get_device_consoles`, step 2 method, existing try/except warning pattern
- [ ] 5. Correct a stored save_path in another profile: in `run_game`, extend the #725 `.bak` self-heal so a Switch `save_path` whose parent folder is not the device profile is dropped; the existing title-ID match then re-picks inside the device profile and persists it via `set_game_device`, or seeding fills it.
  - Files: src/cli/run.py
  - Reuses: #725 self-heal block, `_find_local_switch_save`, `_seed_switch_save`
- [ ] 6. Tests (real SQLite for store/API; filesystem tmp_path for CLI).
- [ ] 7. Docs: GOTCHAS Switch section, CLAUDE.md Switch rule line, ARCHITECTURE consoles columns.

## Checklist
Schema bump: yes (v33). New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
GUI editor for the profile (row is editable via the existing PUT); moving existing save data out of stray profile folders (left untouched).

## Log
