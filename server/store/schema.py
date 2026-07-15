"""Database schema, version, and incremental migrations.

When adding a migration: (1) add a new `if from_version < N:` block in `_migrate`,
(2) bump `_SCHEMA_VERSION` to N, (3) add the new table/column to `_SCHEMA` so fresh
DBs get it without running migrations. Do not add bare try/except ALTERs outside
`_migrate` — warm-start DBs skip `_migrate` entirely via the version check.
"""
from __future__ import annotations

import sqlite3

# Bump whenever a new migration block is added below.
_SCHEMA_VERSION = 17

# Full current schema — used for fresh databases only.  Columns added via
# ALTER TABLE migrations are included here so new installs never run migrations.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    last_ip      TEXT,
    last_seen_at TEXT
);
CREATE TABLE IF NOT EXISTS games (
    slug          TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    console       TEXT DEFAULT '',
    sgdb_game_id  INTEGER
);
CREATE TABLE IF NOT EXISTS consoles (
    id                    TEXT PRIMARY KEY,
    device_id             TEXT NOT NULL REFERENCES devices(id),
    console_name          TEXT NOT NULL,
    shortform_name        TEXT NOT NULL,
    device_game_folder    TEXT NOT NULL DEFAULT '',
    device_save_folder    TEXT NOT NULL DEFAULT '',
    device_state_folder   TEXT NOT NULL DEFAULT '',
    device_emulator       TEXT NOT NULL DEFAULT '',
    device_network_folder TEXT NOT NULL DEFAULT '',
    device_local_folder   TEXT NOT NULL DEFAULT '',
    UNIQUE(device_id, console_name, device_game_folder)
);
CREATE TABLE IF NOT EXISTS game_devices (
    game_slug       TEXT NOT NULL REFERENCES games(slug) ON DELETE CASCADE,
    device_id       TEXT NOT NULL REFERENCES devices(id),
    rom_path        TEXT NOT NULL DEFAULT '',
    save_path       TEXT NOT NULL DEFAULT '',
    launch_command  TEXT NOT NULL DEFAULT '',
    state_path      TEXT NOT NULL DEFAULT '',
    rom_folder_path TEXT NOT NULL DEFAULT '',
    rom_source      TEXT NOT NULL DEFAULT 'local',
    rom_rel_path    TEXT NOT NULL DEFAULT '',
    local_rom_path  TEXT NOT NULL DEFAULT '',
    rom_sha256      TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (game_slug, device_id)
);
CREATE TABLE IF NOT EXISTS saves (
    id         TEXT PRIMARY KEY,
    game_slug  TEXT NOT NULL REFERENCES games(slug) ON DELETE CASCADE,
    device_id  TEXT NOT NULL REFERENCES devices(id),
    hash       TEXT NOT NULL,
    pushed_at  TEXT NOT NULL,
    size       INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS states (
    id         TEXT PRIMARY KEY,
    game_slug  TEXT NOT NULL REFERENCES games(slug) ON DELETE CASCADE,
    device_id  TEXT NOT NULL REFERENCES devices(id),
    hash       TEXT NOT NULL,
    pushed_at  TEXT NOT NULL,
    size       INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS locks (
    game_slug   TEXT PRIMARY KEY REFERENCES games(slug) ON DELETE CASCADE,
    device_id   TEXT NOT NULL REFERENCES devices(id),
    acquired_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    type        TEXT NOT NULL,
    game_slug   TEXT,
    device_id   TEXT,
    device_name TEXT,
    rom_path    TEXT,
    occurred_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rom_transfers (
    id               TEXT PRIMARY KEY,
    slug             TEXT NOT NULL REFERENCES games(slug) ON DELETE CASCADE,
    from_device_id   TEXT NOT NULL REFERENCES devices(id),
    to_device_id     TEXT NOT NULL REFERENCES devices(id),
    destination_path TEXT NOT NULL DEFAULT '',
    staged_file      TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'pending',
    queued_at        TEXT NOT NULL,
    completed_at     TEXT,
    sha256           TEXT
);
CREATE TABLE IF NOT EXISTS rom_pull_requests (
    id               TEXT PRIMARY KEY,
    slug             TEXT NOT NULL REFERENCES games(slug) ON DELETE CASCADE,
    from_device_id   TEXT NOT NULL REFERENCES devices(id),
    to_device_id     TEXT NOT NULL REFERENCES devices(id),
    destination_path TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'pending',
    requested_at     TEXT NOT NULL,
    fulfilled_at     TEXT
);
CREATE TABLE IF NOT EXISTS console_defs (
    key              TEXT PRIMARY KEY,
    label            TEXT NOT NULL,
    abbr             TEXT NOT NULL,
    suggestions      TEXT NOT NULL DEFAULT '',
    rom_extensions   TEXT NOT NULL DEFAULT '',
    databases        TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS system_defs (
    extension        TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    save_exts        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS core_defs (
    id               TEXT PRIMARY KEY,
    console_key      TEXT NOT NULL REFERENCES console_defs(key),
    system_extension TEXT NOT NULL REFERENCES system_defs(extension),
    lib_name         TEXT NOT NULL,
    folder_name      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS save_conflicts (
    id                TEXT PRIMARY KEY,
    game_slug         TEXT NOT NULL REFERENCES games(slug) ON DELETE CASCADE,
    winner_device_id  TEXT NOT NULL DEFAULT '',
    loser_device_id   TEXT NOT NULL DEFAULT '',
    winner_hash       TEXT NOT NULL DEFAULT '',
    loser_hash        TEXT NOT NULL DEFAULT '',
    resolved_at       TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'open'
);
CREATE TABLE IF NOT EXISTS console_folder_names (
    console_key      TEXT NOT NULL REFERENCES console_defs(key),
    folder_name      TEXT NOT NULL,
    PRIMARY KEY (console_key, folder_name)
);
CREATE TABLE IF NOT EXISTS standalone_emulators (
    id               TEXT PRIMARY KEY,
    console_key      TEXT NOT NULL REFERENCES console_defs(key),
    label            TEXT NOT NULL,
    native_bins      TEXT NOT NULL DEFAULT '',
    flatpak_id       TEXT,
    flatpak_exec     TEXT,
    save_dir_template TEXT NOT NULL,
    dirs_json        TEXT NOT NULL DEFAULT '{}',
    launch_args      TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS console_saves (
    console_key      TEXT PRIMARY KEY,
    device_id        TEXT NOT NULL,
    hash             TEXT NOT NULL,
    pushed_at        TEXT NOT NULL,
    size             INTEGER NOT NULL,
    card_format      TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS server_settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


_HARMLESS_MIGRATION_MSGS = (
    "duplicate column name",
    "table",  # "table X already exists"
    "no such column",  # DROP COLUMN on already-removed column
    "column",  # catch-all for other column-already-exists variants
)


def _try(conn: sqlite3.Connection, sql: str) -> None:
    """Execute a DDL statement, suppressing only known-harmless OperationalErrors.

    Harmless: duplicate column, table already exists, column not found.
    Any other OperationalError (e.g., SQL syntax) propagates so it isn't hidden.
    """
    try:
        conn.execute(sql)
    except sqlite3.OperationalError as exc:
        msg = str(exc).lower()
        if not any(token in msg for token in _HARMLESS_MIGRATION_MSGS):
            raise


def _migrate_blobs_to_disk(conn: sqlite3.Connection, table: str, blob_dir) -> None:
    """Move every BLOB in *table* out of SQLite into a file under blob_dir/<table>.

    Each row's bytes are written to ``blob_dir/<table>/<row id>`` and its ``size``
    column is populated, so the ``data`` column can be dropped afterwards. Rows are
    read one at a time so a large DB isn't loaded into memory all at once.
    """
    from pathlib import Path

    tdir = Path(blob_dir) / table
    tdir.mkdir(parents=True, exist_ok=True)
    ids = [r["id"] for r in conn.execute(f"SELECT id FROM {table}").fetchall()]
    for blob_id in ids:
        row = conn.execute(f"SELECT data FROM {table} WHERE id = ?", (blob_id,)).fetchone()
        data = bytes(row["data"]) if row and row["data"] is not None else b""
        (tdir / blob_id).write_bytes(data)
        conn.execute(f"UPDATE {table} SET size = ? WHERE id = ?", (len(data), blob_id))


def _migrate(conn: sqlite3.Connection, from_version: int, blob_dir=None) -> None:
    """Apply incremental migrations for databases older than _SCHEMA_VERSION.

    `blob_dir` is the on-disk blob root (``<data_dir>/blobs``); required for the v8
    migration that moves save/state BLOBs out of SQLite onto disk (issue #239).
    """
    if from_version < 1:
        # Add columns that may not exist on pre-versioned databases
        _try(conn, "ALTER TABLE game_devices ADD COLUMN state_path TEXT NOT NULL DEFAULT ''")
        _try(conn, "ALTER TABLE game_devices ADD COLUMN rom_folder_path TEXT NOT NULL DEFAULT ''")
        _try(conn, "ALTER TABLE games ADD COLUMN console TEXT DEFAULT ''")
        _try(conn, "ALTER TABLE devices ADD COLUMN last_ip TEXT")
        _try(conn, "ALTER TABLE devices ADD COLUMN last_seen_at TEXT")
        # Drop the per-device UUID token — auth is now PIN-based (see api.py _auth).
        # SQLite 3.35+ supports DROP COLUMN; the constraint is on 'token' not 'id' so FKs are safe.
        _try(conn, "ALTER TABLE devices DROP COLUMN token")
    if from_version < 2:
        _try(conn, "ALTER TABLE events ADD COLUMN rom_path TEXT")
    if from_version < 3:
        _try(conn, """CREATE TABLE IF NOT EXISTS rom_transfers (
            id               TEXT PRIMARY KEY,
            slug             TEXT NOT NULL REFERENCES games(slug) ON DELETE CASCADE,
            from_device_id   TEXT NOT NULL REFERENCES devices(id),
            to_device_id     TEXT NOT NULL REFERENCES devices(id),
            destination_path TEXT NOT NULL DEFAULT '',
            staged_file      TEXT NOT NULL DEFAULT '',
            status           TEXT NOT NULL DEFAULT 'pending',
            queued_at        TEXT NOT NULL,
            completed_at     TEXT
        )""")
    if from_version < 4:
        _try(conn, """CREATE TABLE IF NOT EXISTS rom_pull_requests (
            id               TEXT PRIMARY KEY,
            slug             TEXT NOT NULL REFERENCES games(slug) ON DELETE CASCADE,
            from_device_id   TEXT NOT NULL REFERENCES devices(id),
            to_device_id     TEXT NOT NULL REFERENCES devices(id),
            destination_path TEXT NOT NULL DEFAULT '',
            status           TEXT NOT NULL DEFAULT 'pending',
            requested_at     TEXT NOT NULL,
            fulfilled_at     TEXT
        )""")
    if from_version < 5:
        _try(conn, """CREATE TABLE IF NOT EXISTS console_defs (
            key              TEXT PRIMARY KEY,
            label            TEXT NOT NULL,
            abbr             TEXT NOT NULL,
            suggestions      TEXT NOT NULL DEFAULT ''
        )""")
        _try(conn, """CREATE TABLE IF NOT EXISTS system_defs (
            extension        TEXT PRIMARY KEY,
            name             TEXT NOT NULL,
            save_exts        TEXT NOT NULL
        )""")
        _try(conn, """CREATE TABLE IF NOT EXISTS core_defs (
            id               TEXT PRIMARY KEY,
            console_key      TEXT NOT NULL REFERENCES console_defs(key),
            system_extension TEXT NOT NULL REFERENCES system_defs(extension),
            lib_name         TEXT NOT NULL,
            folder_name      TEXT NOT NULL
        )""")
        _try(conn, """CREATE TABLE IF NOT EXISTS console_folder_names (
            console_key      TEXT NOT NULL REFERENCES console_defs(key),
            folder_name      TEXT NOT NULL,
            PRIMARY KEY (console_key, folder_name)
        )""")
        _try(conn, """CREATE TABLE IF NOT EXISTS standalone_emulators (
            id               TEXT PRIMARY KEY,
            console_key      TEXT NOT NULL REFERENCES console_defs(key),
            label            TEXT NOT NULL,
            native_bins      TEXT NOT NULL DEFAULT '',
            flatpak_id       TEXT,
            flatpak_exec     TEXT,
            save_dir_template TEXT NOT NULL
        )""")
    if from_version < 6:
        # Add console_key column to core_defs if it doesn't exist
        try:
            conn.execute("SELECT console_key FROM core_defs LIMIT 1")
        except sqlite3.OperationalError:
            # Column doesn't exist, add it
            _try(conn, "ALTER TABLE core_defs ADD COLUMN console_key TEXT REFERENCES console_defs(key)")
            # Clear old core_defs rows without console_key so they'll be re-seeded
            conn.execute("DELETE FROM core_defs WHERE console_key IS NULL")
    if from_version < 7:
        # Record each staged ROM's SHA256 so the receiver can verify its download (issue #214).
        _try(conn, "ALTER TABLE rom_transfers ADD COLUMN sha256 TEXT")
    if from_version < 8:
        # Move save/state BLOBs out of SQLite onto disk to keep the DB small (#239).
        _try(conn, "ALTER TABLE saves ADD COLUMN size INTEGER NOT NULL DEFAULT 0")
        _try(conn, "ALTER TABLE states ADD COLUMN size INTEGER NOT NULL DEFAULT 0")
        if blob_dir is not None:
            for table in ("saves", "states"):
                _migrate_blobs_to_disk(conn, table, blob_dir)
            _try(conn, "ALTER TABLE saves DROP COLUMN data")
            _try(conn, "ALTER TABLE states DROP COLUMN data")
    if from_version < 9:
        # Central record of auto-resolved save divergences for the GUI Conflicts
        # panel (issue #243).
        _try(conn, """CREATE TABLE IF NOT EXISTS save_conflicts (
            id                TEXT PRIMARY KEY,
            game_slug         TEXT NOT NULL REFERENCES games(slug) ON DELETE CASCADE,
            winner_device_id  TEXT NOT NULL DEFAULT '',
            loser_device_id   TEXT NOT NULL DEFAULT '',
            winner_hash       TEXT NOT NULL DEFAULT '',
            loser_hash        TEXT NOT NULL DEFAULT '',
            resolved_at       TEXT NOT NULL,
            status            TEXT NOT NULL DEFAULT 'open'
        )""")
    if from_version < 10:
        # Network-drive ROM source + on-demand local copies (issue #255).
        # Per-console network/local roots (this device's NAS mount + local copy dest).
        _try(conn, "ALTER TABLE consoles ADD COLUMN device_network_folder TEXT NOT NULL DEFAULT ''")
        _try(conn, "ALTER TABLE consoles ADD COLUMN device_local_folder TEXT NOT NULL DEFAULT ''")
        # Per-game source + portable rel-path + localized copy + master hash.
        # Existing rows default to rom_source='local' so current launches are unaffected.
        _try(conn, "ALTER TABLE game_devices ADD COLUMN rom_source TEXT NOT NULL DEFAULT 'local'")
        _try(conn, "ALTER TABLE game_devices ADD COLUMN rom_rel_path TEXT NOT NULL DEFAULT ''")
        _try(conn, "ALTER TABLE game_devices ADD COLUMN local_rom_path TEXT NOT NULL DEFAULT ''")
        _try(conn, "ALTER TABLE game_devices ADD COLUMN rom_sha256 TEXT NOT NULL DEFAULT ''")
    if from_version < 11:
        # Standalone emulators gain an extensible per-emulator dir-template blob
        # (native/flatpak → save/state/memcard templates) so PCSX2 etc. can carry
        # their state + memory-card dirs without further migrations (issue #292).
        _try(conn, "ALTER TABLE standalone_emulators ADD COLUMN dirs_json TEXT NOT NULL DEFAULT '{}'")
    if from_version < 12:
        # PS2/PCSX2 (issue #293): a console's scannable ROM extensions, decoupled
        # from core-derived system_keys, so a standalone-only console (no libretro
        # core, e.g. PS2) still scans the right extensions; and per-emulator launch
        # args so PCSX2 boots with `-batch -fullscreen`.
        _try(conn, "ALTER TABLE console_defs ADD COLUMN rom_extensions TEXT NOT NULL DEFAULT ''")
        _try(conn, "ALTER TABLE standalone_emulators ADD COLUMN launch_args TEXT NOT NULL DEFAULT ''")
    if from_version < 13:
        # Console-scoped shared save: one memory card per console (PS2), shared
        # across every game on that console, reconciled around any launch (#295).
        _try(conn, """CREATE TABLE IF NOT EXISTS console_saves (
            console_key      TEXT PRIMARY KEY,
            device_id        TEXT NOT NULL,
            hash             TEXT NOT NULL,
            pushed_at        TEXT NOT NULL,
            size             INTEGER NOT NULL
        )""")
    if from_version < 14:
        # Generic single-value server-wide settings (issue #322) — currently
        # used for the shared SteamGridDB API key (entered once on the server
        # device, fetched by every connected device), but kept generic so a
        # future single server-wide setting doesn't need its own migration.
        _try(conn, """CREATE TABLE IF NOT EXISTS server_settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        )""")
    if from_version < 15:
        # A manually-picked SteamGridDB game match, remembered per game so
        # every device sees the same pinned artwork source instead of each
        # re-searching independently (issue #325).
        _try(conn, "ALTER TABLE games ADD COLUMN sgdb_game_id INTEGER")
    if from_version < 16:
        # Libretro database names per console (';'-joined, e.g. "Sony -
        # PlayStation"), matched against each installed core's .info `database`
        # field so ANY core for a supported console is recognized without being
        # hardcoded in a core list (issue #400).
        _try(conn, "ALTER TABLE console_defs ADD COLUMN databases TEXT NOT NULL DEFAULT ''")
    if from_version < 17:
        # Dolphin's GC memory card can be either a flat file or a nested
        # GCI-folder tree, user-configured independently per device; a mismatch
        # doesn't crash but silently stops saves from actually propagating
        # between devices (issue #428). Tag each push with the pushing device's
        # configured format so a pulling device can detect a mismatch before
        # merging incompatible card layouts together.
        _try(conn, "ALTER TABLE console_saves ADD COLUMN card_format TEXT NOT NULL DEFAULT ''")
    conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
