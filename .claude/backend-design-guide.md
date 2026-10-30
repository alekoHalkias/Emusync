# Backend design guide

Patterns the Python side actually uses (server/, cli/, emusync.py). Compress past 100 lines by merging, never by dropping a rule.

## Layout and ownership
- `src/server/api/*.py` = one `APIRouter` per domain; `_core.py` holds shared deps (`_auth`, `_get_store`, `_print_activity`). Routes stay thin: authenticate, call a Store method, return dicts.
- `src/server/store/*.py` = one mixin per table-group, mixed into `Store`, operating on `self._conn`. Shared helpers (e.g. `upsert_console_for_game`, `saves_path_to_states`) live in the mixin module and are re-exported by `src/server/store/__init__.py`.
- `src/server/store/models.py` = row-shaped dataclasses, one field per column, defaults for everything added after the original table.
- `src/cli/*.py` = Click, one module per command group. A CLI command that shows server state goes through the HTTP client (`_client()`), never a local Store - the local DB is not the server's on a paired device.

## Store conventions
- SQL is written inline with the full column list in both `INSERT` and `SELECT`; there is no generated-SQL helper. Adding a column means editing every one of those literals for that table (`set_*`, `get_*`, `list_*`).
- Insert-or-ignore for records, explicit `update_*` for renames. Fill-only-blank semantics for inferred fields so a later save/state update cannot blank a hand-edited value.
- List/dict payloads in SQLite use a JSON TEXT column with a `NOT NULL DEFAULT` and `json.dumps`/`json.loads` at the boundary (`standalone_emulators.dirs_json`). Never a comma-joined string.
- Only PS2/DC/GC/PSP/3DS use the shared memcard tables; that set is DB-backed `console_defs`, never hardcoded.

## Schema evolution
1. add the table/column to `_SCHEMA` (fresh DB), 2. bump `_SCHEMA_VERSION`, 3. add an `if from_version < N:` block with `_try(conn, "ALTER TABLE ...")`, 4. keep the trailing `PRAGMA user_version = _SCHEMA_VERSION`. Never rename or drop a column; `no such column` means delete `emusync.db`.

## API conventions
- Request bodies are pydantic `BaseModel`s with every field defaulted, so an old client still validates. A PUT that edits a record replaces the whole field set; fields that must survive a blank request are handled explicitly (preserve-if-empty), and the docstring says which behavior applies. New list fields on such a PUT are `Optional[list[str]] = None` and `None` means preserve (`model_dump(exclude_none=True)`), so an older client cannot blank them.
- Errors are `HTTPException` with a short human sentence. Auth for "this device only" edits compares `target_device_id != device_id`.

## Backwards compatibility
Additive is allowed (new column with default, new defaulted request field, new optional key). Renames/removals are breaking: +2 difficulty, transitional path required. Old servers ignore unknown request keys, so new fields must be harmless when dropped.

## Tests
`src/tests/test_integration.py` style: real SQLite, no mocks, `client` fixture, `AUTH` headers (`Bearer <pin>`, `X-Device-ID`, `X-Device-Name`), `EMUSYNC_CONFIG_DIR` isolation, blank PIN means `init(Store(tmpdir), "")`. New API route gets happy path plus its main error; new Store method and every bug fix get a regression test.
