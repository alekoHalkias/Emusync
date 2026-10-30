# Handoff: #629 Console settings model: consolidate ROM/local-copy folders, real emulator dropdown, extra ROM folder management

## Metadata
- Issue: #629
- Branch: feature/629-console-settings-model
- PR: none
- Status: implementing
- Created: 2026-10-29
- Fix attempts: 0

## 1. Issue
### Summary
The per-console folder editor (`ConsoleFoldersModal`) presents six flat fields (ROM folder, Save folder, States folder, Emulator, Network (NAS) folder, Local copy folder) and gets three things wrong: ROM folder and local copy folder read as peers, extra ROM paths have nowhere to live, and the emulator value is derived rather than chosen.

### Motivation
The console settings model is the primary way a user tells EmuSync where their files are. As it stands the field list is ambiguous, users cannot pick their emulator, and games spread across several folders cannot be represented. Users work around it in the CLI or not at all.

### Proposed Behavior / Steps to Reproduce
1. Open ConsoleFoldersModal for any console on a device.
2. ROM folder and Local copy folder appear as two equal fields; nothing says the second one is the destination for network ROMs.
3. There is no section for additional ROM folders; only `device_game_folder` exists.
4. The Emulator field is text auto-filled by `upsert_console_for_game` from the save-folder basename; the user cannot select it.

### Affected Area
- `src/gui/renderer/src/components/ConsoleFoldersModal.tsx` - the modal UI and its field grouping
- `src/gui/renderer/src/components/GameConfig.tsx` - per-game settings that duplicate the emulator/folder concepts
- `src/gui/renderer/src/api.ts`, `src/gui/renderer/src/emusync.d.ts` - `DeviceConsole` type, `updateDeviceConsole`
- `src/gui/electron/emulator/detect.ts` (`detectEmulatorsForConsole`), `src/gui/electron/emulator/ipc.ts` - existing emulator option list
- `src/server/store/consoles.py` (`ConsoleDevice`/`upsert_console_for_game`), `src/server/store/models.py`, `src/server/store/schema.py` - consoles table
- `src/server/api/devices.py` - `ConsoleFoldersRequest` / PUT endpoint
- Related closed work: #539 (per-console folder settings), #618/#622/#624/#626 (ROM source local/network, move-to-console-folder, add-to-network, bulk)

### Acceptance Criteria
- [ ] ROM folder and local copy folder are no longer presented as two peer fields; each is labeled for what it actually does.
- [ ] Extra ROM folders (beyond the console default) have their own section at the bottom of the modal, with add/remove capability.
- [ ] Emulator is a single per-console selection backed by a real dropdown (RetroArch cores + detected standalone emulators), not a derived text field.
- [ ] The derived-emulator behavior in `upsert_console_for_game` no longer overwrites a user-chosen emulator.
- [ ] Existing local/network ROM source resolution (#618 prefixes, #622 move panel, #624 upload, #626 bulk) keeps working after the model changes.
- [ ] `make test-changed` passes; new REST surface gets an integration test.

## 2. Design
### Scope: Medium-large. One new `consoles` column plus one shared upsert behavior change on the Python side; a full reorganization of `ConsoleFoldersModal` plus two small type/consumer changes on the GUI side. Emulator stays label-only, so the launch path is untouched.

User decisions (asked before design was finished):
1. ROM folder / local copy folder: one primary "ROM folder" field. The copy-destination field renders only when `device_network_folder` is set, and when it is blank it displays the ROM folder as its effective value. `device_local_folder` keeps its DB meaning and every existing consumer stays untouched.
2. Extra ROM folders: a new `device_extra_folders` column on the primary row (not the legacy multi-row model).
3. Emulator selection: label only. Nothing reads `device_emulator` at runtime; per-game `launch_command` (including the `%ROM%` token, #518) is not rewritten.
4. Layout: one block per console, extras in their own section at the bottom.

### Backend Changes
- `src/server/store/schema.py`: `_SCHEMA_VERSION` 28 -> 29; `device_extra_folders TEXT NOT NULL DEFAULT '[]'` on `consoles` in `_SCHEMA`; `if from_version < 29:` block with `_try(conn, "ALTER TABLE consoles ADD COLUMN ...")`; keep the fresh-DB `PRAGMA user_version` stamp. Follow the `console_defs.dirs_json` JSON-text precedent.
- `src/server/store/models.py`: `Console.device_extra_folders: list[str] = []`.
- `src/server/store/consoles.py`: `set_console`/`get_console`/`list_consoles` SQL gains the column; `json.dumps`/`json.loads` at that boundary so the model stays a list. `upsert_console_for_game` matches an existing row by `console_name` first; a game folder that differs from that row's `device_game_folder` is appended to `device_extra_folders` instead of creating a second row. One function, so CLI `game add` and `PUT /games/{slug}/device` both change at once.
- `src/server/api/devices.py`: `GET /devices/{id}/consoles` returns `device_extra_folders`; `ConsoleFoldersRequest` gains `device_extra_folders: list[str] = []` and PUT sets it (default keeps pre-#629 clients working).
- Optional, not required: `cli/console.py` list output showing the extra folders.
- Known gap, deliberately out of scope: `sync_client.py`'s `GameDeviceConfig` does not carry extra folders, so a second device does not learn them over the wire.

### UI Changes
- `src/gui/renderer/src/components/ConsoleFoldersModal.tsx`: group `rows` by `console_name` (one block per console; extras merged), render ROM / Save / States / Emulator / Network, render the copy destination only when a network folder is set, and put "Other ROM folders" at the bottom with Add and Remove. `FIELDS` is currently a flat array driving one flat form, so this is a rewrite of that component's body, not a new component.
- Emulator dropdown from the already-registered `emulator:detect` IPC (`src/gui/electron/emulator/ipc.ts` returns `detectEmulatorsForConsole` options) - no new IPC channel, no `emusync.d.ts` change.
- `src/gui/renderer/src/api.ts`: `DeviceConsole` and `updateDeviceConsole` payload gain `device_extra_folders`.
- `src/gui/renderer/src/components/game-list/useBrokenRoms.ts`: `sourceFor()` gains the extra folders as local candidates so Refresh, the broken-ROM badge (#616) and the #618 local/network classification treat them as real local ROM locations.
- `GameConfig.tsx`, `MoveLocalRomPanel.tsx`, `NetworkRomPanel.tsx`, `localToNetwork.ts`: read-through only, no change unless extra folders need to appear in their panels.

### Plan Target: both
### Sub-issues: none. The natural split (UI-only folder consolidation vs backend extra-folder storage) would redo the same schema change and the same modal rewrite twice.
### Difficulty: 6/10 (schema bump plus a shared-function behavior change plus a modal rewrite; no breaking change, no launch-path change)
### Backwards Compatibility: no breaking changes. Column and request field are additive with defaults; an old server ignores `device_extra_folders`. Legacy one-row-per-folder console rows stay in the DB and are surfaced in the "Other ROM folders" list, never rewritten or deleted, so `UNIQUE(device_id, console_name, device_game_folder)` is untouched. `device_local_folder` keeps its meaning and all consumers of it are untouched. No IPC channel added or changed.

## 3. Frontend Plan
### Design Alignment: Keeps the Modal/config-form/input-group pattern; plain select for the emulator; list rows with ghost Remove. Plan file: tools/plans/629-console-settings-model-ui.md
### Visual Pattern: Single block per console, conditional copy-destination field, extras section at bottom, one Save/PUT.
### Recommendations: Guide gained a Settings forms entry. Legacy extra console rows are read-only (no delete route).

## 4. Backend Plan
### Design Alignment: Fits the guide: additive JSON-TEXT column (dirs_json precedent), schema evolution steps 1-4, defaulted pydantic field, single shared inference function. Plan file: tools/plans/629-console-settings-model.md
### Backend Pattern: JSON list column at the Store boundary; PUT list field Optional/None = preserve; upsert routes a differing game folder into extras instead of a new row.
### Recommendations: Guide updated with the Optional-means-preserve rule. device_emulator needs no backend change (already fill-only-blank); pinned by a regression test.

## 5. Merged Plan
### Conflicts Resolved: docs steps (CLAUDE.md, ARCHITECTURE.md) merged into one; backend-first ordering; PUT Optional/None field compatible with full-list frontend send; backend normalizes extras. Merged plan: tools/plans/629-console-settings-model.md (13 steps).
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: src/tests/test_devices.py (API + upsert), src/tests/test_network_rom.py (migration, network guard). No new files or fixtures.
### Test Cases: extras default [], round-trip, normalization, preserve-on-omit (regression), upsert routing to extras, emulator survives, v28 migration (7)
### Edge Cases: same-folder repeat, save-only game, legacy two-row console, network-folder guard, first-ever game unchanged, PUT 403/404 unchanged (6)
### Integration Points: PUT /games/{slug}/device -> upsert -> GET consoles; two existing regression tests must pass unchanged; GUI via make lint + manual run

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps (bplan)
- 1. [done] schema.py, models.py. Reuses `_try` ALTER pattern. New: none.
- 2. [done] consoles.py set/get/list SQL + JSON. Reuses console_defs json usage. New: `_console_from_row` (get and list both parse JSON).
- 3. [done] consoles.py `upsert_console_for_game` routing (+ tplan: skip folders inside device_network_folder). Reuses existing lookup + fill-only-blank. New: none.
- 4. devices.py GET + PUT. Reuses model_dump setattr loop (+exclude_none). New: none.
- 5. test_devices.py, test_network_rom.py: 9 cases (tplan added network-folder guard) (see plan file). Reuses `_seed_console`, migration test pattern.
- 6. ARCHITECTURE.md, CLAUDE.md. New: none.
### Steps (fplan)
- F1. api.ts DeviceConsole + device_extra_folders. Reuses existing type/fn. New: none.
- F2. useBrokenRoms.ts sourceFor adds extras as local candidates. Reuses candidates array. New: none.
- F3. ConsoleFoldersModal.tsx group/fields/copy field. Reuses edit/browse/save, usesSharedSaveLayout. New: none.
- F4. Same file: emulator select from emulator:detect. Reuses existing IPC, ConsoleStep markup. New: none.
- F5. Same file: Other ROM folders section. Reuses browse + dialog.openFolder. New: none.
- F6. Same file: replace stale helper text.
- F7. make lint + run skill manual check (no JS test runner exists).
- F8. frontend-design-guide.md, CLAUDE.md, ARCHITECTURE.md.

## 9. Review
### Findings: TBD
### Blocked: TBD
### Blockers: TBD

## 10. Ship
### Status: pending
### PR: none
### Server Sync: pending
### Doc Sync: pending

## 11. Fix Attempts
### Attempt 1: none
### Attempt 2: none
### Attempt 3: none

## 12. Log
- 2026-10-29 issue: workflow initialized (issue #629 filed, handoff created)
- 2026-10-29 issue: duplicate check found #628 and #629; user chose to continue under #629. #628 and feature/628-console-settings-model are now superseded, neither has code changes.
- 2026-10-29 bplan: 6 steps written, backend_pattern=JSON extras column + Optional-preserve PUT field + upsert routes differing folder to extras
- 2026-10-29 fplan: 8 steps written, visual_pattern=single console block, conditional copy field, emulator select, extras list
- 2026-10-29 merge: 4 conflicts resolved, 0 unresolved
- 2026-10-29 tplan: test_file=src/tests/test_devices.py + test_network_rom.py, 7 test cases + 6 edge cases defined; plan step 3 amended with network-folder guard
- 2026-10-29 implement: step 1 done (schema v29 column + Console.device_extra_folders)
- 2026-10-29 implement: step 2 done (store reads/writes extras as JSON via _console_from_row)
- 2026-10-29 implement: step 3 done (upsert routes unknown folders to extras; deviation: nested-folder skip, blank primary fill)
