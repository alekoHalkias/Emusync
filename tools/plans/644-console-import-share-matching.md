# Plan: #644 Redesign console import modal with optional network folder and share matching

Issue: #644
Branch: feature/644-console-import-share-matching
PR: none
Status: implementing
Fix attempts: 0

## Goal
Store a per-device-console network share ID and expose other devices' share IDs so the client can validate that two differently-mounted network folders are the same share.

## Design Alignment
- **Backend Pattern**: additive column on `consoles` following the schema-evolution recipe; response field plus `Optional[str] = None` (preserve) request field on the existing console PUT; one thin read route backed by one Store method.
- **Recommendations**: Auto-link needs no new server logic. The ROM scan already sets `linkedSlug` by name for ROMs matching existing games, and `resolveImportPaths` already derives rom_rel_path, save and launch paths on the client. After a share match, the GUI (fplan) scans the network folder and imports the linked entries through the existing path. Server stays a registry of share IDs. #643 is closed as superseded, so there is no `import_remote_path` on main to remove.

## Steps
- [ ] 1. Add `consoles.network_share_id` (TEXT NOT NULL DEFAULT '') to the model, `_SCHEMA`, migration `from_version < 30`, `_SCHEMA_VERSION = 30`, and every consoles SQL literal.
  - Files: src/server/store/models.py, src/server/store/schema.py, src/server/store/consoles.py
  - Reuses: schema.py `_try` ALTER pattern; `_console_from_row`; the existing set_console/get_console/list_consoles literals
  - New: none - column only
- [ ] 2. Store method `list_console_shares(console_name, exclude_device_id)` returning `[{device_id, device_name, share_id}]` for other devices with a non-empty share ID for that console name.
  - Files: src/server/store/consoles.py
  - Reuses: consoles/devices tables join as in get_network_source_for_game
  - New: one query - no existing cross-device console lookup
- [ ] 3. API: include `network_share_id` in `GET /devices/{id}/consoles`; add `network_share_id: Optional[str] = None` to `ConsoleFoldersRequest` (None = preserve via existing `exclude_none`); add `GET /consoles/{console_name}/shares` calling step 2.
  - Files: src/server/api/devices.py
  - Reuses: update_device_console's `model_dump(exclude_none=True)` loop; `_auth`, `_get_store`
  - New: one route - nothing existing lists other devices' consoles
- [ ] 4. Tests (real SQLite): migration from v29 adds column with '' default and preserves rows; PUT stores share ID and a PUT without it preserves it; `/consoles/{name}/shares` returns other devices only, skips blank IDs, and a mismatch case; 403 editing another device's console still holds.
  - Files: src/tests/test_integration.py (or existing console test module)
  - Reuses: `client` fixture, `AUTH` headers
- [ ] 5. Docs: ARCHITECTURE.md (consoles column, new route); CLAUDE.md rule line on share identity via marker file and `network_share_id`.
  - Files: src/docs/ARCHITECTURE.md, CLAUDE.md

## Checklist
Schema bump: yes (29 -> 30). New IPC channel (+ emusync.d.ts): no (backend; fplan adds marker IPC). New CLI subcommand: no. Config/data file change: no.

## Not in this plan
Marker file read/write, chips, toast, Locations UI, auto-link orchestration (fplan). Server-side game linking. Dropping columns.

## Log
