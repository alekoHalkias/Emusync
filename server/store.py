from __future__ import annotations

import hashlib
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

LOCK_TTL_HOURS = 4


class _LockedConnection:
    """Wraps sqlite3.Connection and serializes all access via a lock."""

    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock) -> None:
        self._conn = conn
        self._lock = lock

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            return self._conn.execute(*args, **kwargs)

    def commit(self) -> None:
        with self._lock:
            return self._conn.commit()

    def __getattr__(self, name: str) -> Any:
        with self._lock:
            return getattr(self._conn, name)

# Bump whenever a new migration block is added below.
_SCHEMA_VERSION = 6

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
    slug    TEXT PRIMARY KEY,
    name    TEXT NOT NULL,
    console TEXT DEFAULT ''
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
    PRIMARY KEY (game_slug, device_id)
);
CREATE TABLE IF NOT EXISTS saves (
    id         TEXT PRIMARY KEY,
    game_slug  TEXT NOT NULL REFERENCES games(slug) ON DELETE CASCADE,
    device_id  TEXT NOT NULL REFERENCES devices(id),
    data       BLOB NOT NULL,
    hash       TEXT NOT NULL,
    pushed_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS states (
    id         TEXT PRIMARY KEY,
    game_slug  TEXT NOT NULL REFERENCES games(slug) ON DELETE CASCADE,
    device_id  TEXT NOT NULL REFERENCES devices(id),
    data       BLOB NOT NULL,
    hash       TEXT NOT NULL,
    pushed_at  TEXT NOT NULL
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
    completed_at     TEXT
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
    suggestions      TEXT NOT NULL DEFAULT ''
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
    save_dir_template TEXT NOT NULL
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


def _migrate(conn: sqlite3.Connection, from_version: int) -> None:
    """Apply incremental migrations for databases older than _SCHEMA_VERSION."""
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
    conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")


@dataclass
class Device:
    id: str
    name: str
    last_ip: Optional[str] = None
    last_seen_at: Optional[str] = None


@dataclass
class Game:
    slug: str
    name: str
    console: str = ""


@dataclass
class Console:
    id: str
    device_id: str
    console_name: str
    shortform_name: str
    device_game_folder: str = ""
    device_save_folder: str = ""
    device_state_folder: str = ""
    device_emulator: str = ""


@dataclass
class GameDevice:
    game_slug: str
    device_id: str
    rom_path: str
    save_path: str
    launch_command: str
    state_path: str = ""
    rom_folder_path: str = ""


@dataclass
class SaveMeta:
    game_slug: str
    device_id: str
    hash: str
    pushed_at: str


@dataclass
class Lock:
    game_slug: str
    device_id: str
    acquired_at: str


@dataclass
class RomTransfer:
    id: str
    slug: str
    from_device_id: str
    to_device_id: str
    destination_path: str
    staged_file: str
    status: str
    queued_at: str
    completed_at: Optional[str] = None


@dataclass
class RomPullRequest:
    id: str
    slug: str
    from_device_id: str
    to_device_id: str
    destination_path: str
    status: str
    requested_at: str
    fulfilled_at: Optional[str] = None


class Store:
    def __init__(self, data_dir: str) -> None:
        db_path = Path(data_dir) / "emusync.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        is_fresh = not db_path.exists()
        self._lock = threading.RLock()
        raw_conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=30.0)
        raw_conn.row_factory = sqlite3.Row
        self._conn = _LockedConnection(raw_conn, self._lock)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.commit()
        if is_fresh:
            # Split schema statements and execute individually (executescript() incompatible with WAL)
            for statement in _SCHEMA.split(";"):
                statement = statement.strip()
                if statement:
                    self._conn.execute(statement)
                    self._conn.commit()
        db_version: int = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if db_version < _SCHEMA_VERSION:
            _migrate(raw_conn, db_version)
        self._conn.commit()

    # ── devices ──────────────────────────────────────────────────────────────

    def ensure_device(self, id: str, name: str) -> tuple[Device, bool]:
        """Register a device if new; update name if it changed. Idempotent.

        Returns (device, is_new) where is_new is True on first-ever registration.
        """
        cursor = self._conn.execute(
            "INSERT OR IGNORE INTO devices (id, name) VALUES (?, ?)", (id, name)
        )
        is_new = cursor.rowcount > 0
        if not is_new:
            self._conn.execute("UPDATE devices SET name = ? WHERE id = ?", (name, id))
        self._conn.commit()
        return Device(id=id, name=name), is_new

    def clear_devices(self) -> None:
        self._conn.execute("DELETE FROM devices")
        self._conn.commit()

    def list_devices(self) -> list[Device]:
        rows = self._conn.execute(
            "SELECT id, name, last_ip, last_seen_at FROM devices"
        ).fetchall()
        return [Device(**dict(r)) for r in rows]

    def touch_device(self, device_id: str, ip: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE devices SET last_ip = ?, last_seen_at = ? WHERE id = ?",
            (ip, now, device_id),
        )
        self._conn.commit()

    def remove_device(self, device_id: str) -> None:
        self._conn.execute("DELETE FROM devices WHERE id = ?", (device_id,))
        self._conn.commit()

    # ── consoles ──────────────────────────────────────────────────────────────

    def set_console(self, console: Console) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO consoles
               (id, device_id, console_name, shortform_name, device_game_folder, device_save_folder, device_state_folder, device_emulator)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (console.id, console.device_id, console.console_name, console.shortform_name,
             console.device_game_folder, console.device_save_folder, console.device_state_folder, console.device_emulator),
        )
        self._conn.commit()

    def get_console(self, device_id: str, console_name: str) -> Optional[Console]:
        row = self._conn.execute(
            """SELECT id, device_id, console_name, shortform_name, device_game_folder, device_save_folder, device_state_folder, device_emulator
               FROM consoles WHERE device_id = ? AND console_name = ?""",
            (device_id, console_name),
        ).fetchone()
        return Console(**dict(row)) if row else None

    def list_consoles(self, device_id: str) -> list[Console]:
        rows = self._conn.execute(
            """SELECT id, device_id, console_name, shortform_name, device_game_folder, device_save_folder, device_state_folder, device_emulator
               FROM consoles WHERE device_id = ?""",
            (device_id,),
        ).fetchall()
        return [Console(**dict(r)) for r in rows]

    def remove_console(self, console_id: str) -> None:
        self._conn.execute("DELETE FROM consoles WHERE id = ?", (console_id,))
        self._conn.commit()

    # ── games ─────────────────────────────────────────────────────────────────

    def add_game(self, slug: str, name: str, console: str = "") -> Game:
        self._conn.execute(
            "INSERT OR IGNORE INTO games (slug, name, console) VALUES (?, ?, ?)", (slug, name, console)
        )
        self._conn.commit()
        return Game(slug=slug, name=name, console=console)

    def update_game_name(self, slug: str, name: str) -> None:
        """Rename a game without touching its saves, locks, or device config."""
        self._conn.execute(
            "UPDATE games SET name = ? WHERE slug = ?", (name, slug)
        )
        self._conn.commit()

    def update_game_console(self, slug: str, console: str) -> None:
        """Update the console type for a game."""
        self._conn.execute(
            "UPDATE games SET console = ? WHERE slug = ?", (console, slug)
        )
        self._conn.commit()

    def remove_game(self, slug: str) -> None:
        self._conn.execute("DELETE FROM games WHERE slug = ?", (slug,))
        self._conn.commit()

    def list_games(self) -> list[Game]:
        rows = self._conn.execute("SELECT slug, name, console FROM games").fetchall()
        return [Game(**dict(r)) for r in rows]

    def get_game(self, slug: str) -> Optional[Game]:
        row = self._conn.execute(
            "SELECT slug, name, console FROM games WHERE slug = ?", (slug,)
        ).fetchone()
        return Game(**dict(row)) if row else None

    # ── game_devices ──────────────────────────────────────────────────────────

    def set_game_device(self, gd: GameDevice) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO game_devices
               (game_slug, device_id, rom_path, save_path, launch_command, state_path, rom_folder_path)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (gd.game_slug, gd.device_id, gd.rom_path, gd.save_path, gd.launch_command, gd.state_path, gd.rom_folder_path),
        )
        self._conn.commit()

    def get_game_device(self, game_slug: str, device_id: str) -> Optional[GameDevice]:
        row = self._conn.execute(
            """SELECT game_slug, device_id, rom_path, save_path, launch_command, state_path, rom_folder_path
               FROM game_devices WHERE game_slug = ? AND device_id = ?""",
            (game_slug, device_id),
        ).fetchone()
        return GameDevice(**dict(row)) if row else None

    def list_devices_for_game(self, game_slug: str) -> list[dict]:
        rows = self._conn.execute(
            """SELECT d.id, d.name, gd.rom_path, gd.save_path, gd.state_path, gd.rom_folder_path
               FROM game_devices gd
               JOIN devices d ON d.id = gd.device_id
               WHERE gd.game_slug = ?
               ORDER BY d.name""",
            (game_slug,),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "rom_path": row["rom_path"],
                "save_path": row["save_path"],
                "state_path": row["state_path"],
                "rom_folder_path": row["rom_folder_path"],
            }
            for row in rows
        ]

    def list_game_devices_for_device(self, device_id: str) -> list[dict]:
        rows = self._conn.execute(
            """SELECT g.slug, g.name, g.console, gd.rom_path, gd.save_path,
                      gd.launch_command, gd.state_path, gd.rom_folder_path
               FROM game_devices gd
               JOIN games g ON g.slug = gd.game_slug
               WHERE gd.device_id = ?
               ORDER BY g.name""",
            (device_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── saves / states (shared private helpers) ───────────────────────────────

    def _push_blob(self, table: str, game_slug: str, device_id: str, data: bytes) -> SaveMeta:
        h = hashlib.sha256(data).hexdigest()
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(f"DELETE FROM {table} WHERE game_slug = ?", (game_slug,))
        self._conn.execute(
            f"INSERT INTO {table} (id, game_slug, device_id, data, hash, pushed_at) VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), game_slug, device_id, data, h, now),
        )
        self._conn.commit()
        return SaveMeta(game_slug=game_slug, device_id=device_id, hash=h, pushed_at=now)

    def _pull_blob(self, table: str, game_slug: str) -> tuple[Optional[bytes], Optional[SaveMeta]]:
        row = self._conn.execute(
            f"SELECT data, game_slug, device_id, hash, pushed_at FROM {table} WHERE game_slug = ? ORDER BY pushed_at DESC LIMIT 1",
            (game_slug,),
        ).fetchone()
        if not row:
            return None, None
        meta = SaveMeta(
            game_slug=row["game_slug"],
            device_id=row["device_id"],
            hash=row["hash"],
            pushed_at=row["pushed_at"],
        )
        return bytes(row["data"]), meta

    def _get_blob_meta(self, table: str, game_slug: str) -> Optional[SaveMeta]:
        row = self._conn.execute(
            f"SELECT game_slug, device_id, hash, pushed_at FROM {table} WHERE game_slug = ? ORDER BY pushed_at DESC LIMIT 1",
            (game_slug,),
        ).fetchone()
        return SaveMeta(**dict(row)) if row else None

    # ── saves ─────────────────────────────────────────────────────────────────

    def push_save(self, game_slug: str, device_id: str, data: bytes) -> SaveMeta:
        return self._push_blob("saves", game_slug, device_id, data)

    def pull_save(self, game_slug: str) -> tuple[Optional[bytes], Optional[SaveMeta]]:
        return self._pull_blob("saves", game_slug)

    def get_save_meta(self, game_slug: str) -> Optional[SaveMeta]:
        return self._get_blob_meta("saves", game_slug)

    # ── states ─────────────────────────────────────────────────────────────────

    def push_state(self, game_slug: str, device_id: str, data: bytes) -> SaveMeta:
        return self._push_blob("states", game_slug, device_id, data)

    def pull_state(self, game_slug: str) -> tuple[Optional[bytes], Optional[SaveMeta]]:
        return self._pull_blob("states", game_slug)

    def get_state_meta(self, game_slug: str) -> Optional[SaveMeta]:
        return self._get_blob_meta("states", game_slug)

    # ── locks ─────────────────────────────────────────────────────────────────

    def acquire_lock(self, game_slug: str, device_id: str) -> None:
        now = datetime.now(timezone.utc)
        row = self._conn.execute(
            "SELECT device_id, acquired_at FROM locks WHERE game_slug = ?", (game_slug,)
        ).fetchone()
        if row:
            holder = row["device_id"]
            acquired = datetime.fromisoformat(row["acquired_at"])
            if acquired.tzinfo is None:
                acquired = acquired.replace(tzinfo=timezone.utc)
            age_hours = (now - acquired).total_seconds() / 3600
            if holder == device_id:
                self._conn.execute(
                    "UPDATE locks SET acquired_at = ? WHERE game_slug = ?",
                    (now.isoformat(), game_slug),
                )
                self._conn.commit()
                return
            if age_hours < LOCK_TTL_HOURS:
                raise ValueError(f"Game is locked by device {holder}")
        self._conn.execute(
            "INSERT OR REPLACE INTO locks (game_slug, device_id, acquired_at) VALUES (?, ?, ?)",
            (game_slug, device_id, now.isoformat()),
        )
        self._conn.commit()

    def release_lock(self, game_slug: str, device_id: str) -> None:
        self._conn.execute(
            "DELETE FROM locks WHERE game_slug = ? AND device_id = ?",
            (game_slug, device_id),
        )
        self._conn.commit()

    # ── events ────────────────────────────────────────────────────────────────

    def log_event(self, event_type: str, game_slug: Optional[str] = None, device_id: Optional[str] = None, rom_path: Optional[str] = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        device_name: Optional[str] = None
        if device_id:
            row = self._conn.execute("SELECT name FROM devices WHERE id = ?", (device_id,)).fetchone()
            device_name = row["name"] if row else device_id
        self._conn.execute(
            "INSERT INTO events (type, game_slug, device_id, device_name, rom_path, occurred_at) VALUES (?, ?, ?, ?, ?, ?)",
            (event_type, game_slug, device_id, device_name, rom_path, now),
        )
        self._conn.commit()

    def list_events(self, limit: int = 100) -> list[dict]:
        rows = self._conn.execute(
            "SELECT type, game_slug, device_id, device_name, rom_path, occurred_at FROM events ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_lock(self, game_slug: str) -> Optional[Lock]:
        row = self._conn.execute(
            "SELECT game_slug, device_id, acquired_at FROM locks WHERE game_slug = ?",
            (game_slug,),
        ).fetchone()
        return Lock(**dict(row)) if row else None

    # ── rom_transfers ─────────────────────────────────────────────────────────

    def create_rom_transfer(
        self,
        id: str,
        slug: str,
        from_device_id: str,
        to_device_id: str,
        destination_path: str,
        staged_file: str,
    ) -> RomTransfer:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT INTO rom_transfers
               (id, slug, from_device_id, to_device_id, destination_path, staged_file, status, queued_at)
               VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (id, slug, from_device_id, to_device_id, destination_path, staged_file, now),
        )
        self._conn.commit()
        return RomTransfer(
            id=id, slug=slug, from_device_id=from_device_id, to_device_id=to_device_id,
            destination_path=destination_path, staged_file=staged_file,
            status="pending", queued_at=now,
        )

    def get_rom_transfer(self, transfer_id: str) -> Optional[RomTransfer]:
        row = self._conn.execute(
            """SELECT id, slug, from_device_id, to_device_id, destination_path,
                      staged_file, status, queued_at, completed_at
               FROM rom_transfers WHERE id = ?""",
            (transfer_id,),
        ).fetchone()
        return RomTransfer(**dict(row)) if row else None

    def list_pending_transfers_for_device(self, device_id: str) -> list[RomTransfer]:
        rows = self._conn.execute(
            """SELECT id, slug, from_device_id, to_device_id, destination_path,
                      staged_file, status, queued_at, completed_at
               FROM rom_transfers WHERE to_device_id = ? AND status = 'pending'
               ORDER BY queued_at""",
            (device_id,),
        ).fetchall()
        return [RomTransfer(**dict(r)) for r in rows]

    def update_transfer_status(self, transfer_id: str, status: str) -> None:
        completed_at = datetime.now(timezone.utc).isoformat() if status in ("completed", "failed") else None
        self._conn.execute(
            "UPDATE rom_transfers SET status = ?, completed_at = ? WHERE id = ?",
            (status, completed_at, transfer_id),
        )
        self._conn.commit()

    # ── rom pull requests ─────────────────────────────────────────────────────

    def create_pull_request(
        self,
        id: str,
        slug: str,
        from_device_id: str,
        to_device_id: str,
        destination_path: str,
    ) -> RomPullRequest:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT INTO rom_pull_requests
               (id, slug, from_device_id, to_device_id, destination_path, status, requested_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?)""",
            (id, slug, from_device_id, to_device_id, destination_path, now),
        )
        self._conn.commit()
        return RomPullRequest(
            id=id, slug=slug, from_device_id=from_device_id, to_device_id=to_device_id,
            destination_path=destination_path, status="pending", requested_at=now,
        )

    def get_pull_request(self, pull_request_id: str) -> Optional[RomPullRequest]:
        row = self._conn.execute(
            """SELECT id, slug, from_device_id, to_device_id, destination_path,
                      status, requested_at, fulfilled_at
               FROM rom_pull_requests WHERE id = ?""",
            (pull_request_id,),
        ).fetchone()
        return RomPullRequest(**dict(row)) if row else None

    def list_pending_pull_requests_for_device(self, device_id: str) -> list[RomPullRequest]:
        """Return pending pull requests where this device is the source (from_device_id)."""
        rows = self._conn.execute(
            """SELECT id, slug, from_device_id, to_device_id, destination_path,
                      status, requested_at, fulfilled_at
               FROM rom_pull_requests WHERE from_device_id = ? AND status = 'pending'
               ORDER BY requested_at""",
            (device_id,),
        ).fetchall()
        return [RomPullRequest(**dict(r)) for r in rows]

    def update_pull_request_status(self, pull_request_id: str, status: str) -> None:
        fulfilled_at = datetime.now(timezone.utc).isoformat() if status in ("fulfilled", "failed") else None
        self._conn.execute(
            "UPDATE rom_pull_requests SET status = ?, fulfilled_at = ? WHERE id = ?",
            (status, fulfilled_at, pull_request_id),
        )
        self._conn.commit()

    # ── console definitions (source of truth) ──────────────────────────────────

    def seed_console_defs(self, consoles_data: list[dict]) -> None:
        """Populate console definition tables from structured data. Idempotent."""
        for console in consoles_data:
            key = console["key"]
            existing = self._conn.execute(
                "SELECT key FROM console_defs WHERE key = ?", (key,)
            ).fetchone()
            if existing:
                continue
            self._conn.execute(
                "INSERT INTO console_defs (key, label, abbr, suggestions) VALUES (?, ?, ?, ?)",
                (key, console["label"], console.get("abbr", key.upper()),
                 ";".join(console.get("suggestions", [])))
            )
            for sys_key in console["system_keys"]:
                sys_info = console["systems"].get(sys_key)
                if not sys_info:
                    continue
                sys_existing = self._conn.execute(
                    "SELECT extension FROM system_defs WHERE extension = ?", (sys_key,)
                ).fetchone()
                if not sys_existing:
                    self._conn.execute(
                        "INSERT INTO system_defs (extension, name, save_exts) VALUES (?, ?, ?)",
                        (sys_key, sys_info["name"], ";".join(sys_info["save_exts"]))
                    )
                    for core in sys_info.get("cores", []):
                        self._conn.execute(
                            "INSERT INTO core_defs (id, console_key, system_extension, lib_name, folder_name) VALUES (?, ?, ?, ?, ?)",
                            (f"{sys_key}-{core['lib']}", key, sys_key, core["lib"], core["folder"])
                        )
            for folder_name in console.get("folder_names", []):
                self._conn.execute(
                    "INSERT OR IGNORE INTO console_folder_names (console_key, folder_name) VALUES (?, ?)",
                    (key, folder_name)
                )
            for standalone in console.get("standalones", []):
                self._conn.execute(
                    "INSERT OR IGNORE INTO standalone_emulators (id, console_key, label, native_bins, flatpak_id, flatpak_exec, save_dir_template) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (f"{key}-{standalone['id']}", key, standalone["label"],
                     ";".join(standalone.get("native_bins", [])),
                     standalone.get("flatpak_id", ""),
                     standalone.get("flatpak_exec", ""),
                     standalone.get("save_dir_template", ""))
                )
        self._conn.commit()

    def get_console_defs(self) -> list[dict]:
        """Return all console definitions with systemKeys and standalones."""
        rows = self._conn.execute("SELECT key, label, abbr, suggestions FROM console_defs ORDER BY key").fetchall()
        result = []
        for row in rows:
            console_key = row["key"]
            # Get system extensions (keys) for this console
            system_rows = self._conn.execute(
                "SELECT DISTINCT system_extension FROM core_defs WHERE console_key = ? ORDER BY system_extension",
                (console_key,)
            ).fetchall()
            system_keys = [r["system_extension"] for r in system_rows]

            # Get standalone emulators for this console
            standalone_rows = self._conn.execute(
                "SELECT id, label, native_bins, flatpak_id, flatpak_exec, save_dir_template FROM standalone_emulators WHERE console_key = ? ORDER BY label",
                (console_key,)
            ).fetchall()
            standalones = []
            for sr in standalone_rows:
                standalones.append({
                    "id": sr["id"],
                    "label": sr["label"],
                    "native_bins": sr["native_bins"].split(";") if sr["native_bins"] else [],
                    "flatpak_id": sr["flatpak_id"],
                    "flatpak_exec": sr["flatpak_exec"],
                    "save_dir_template": sr["save_dir_template"],
                })

            result.append({
                "key": console_key,
                "label": row["label"],
                "abbr": row["abbr"],
                "suggestions": row["suggestions"],
                "systemKeys": system_keys,
                "standalones": standalones,
            })
        return result

    def get_system_defs(self) -> dict[str, dict]:
        """Return all system definitions keyed by extension."""
        rows = self._conn.execute("SELECT extension, name, save_exts FROM system_defs").fetchall()
        result = {}
        for row in rows:
            ext = row["extension"]
            cores = self._conn.execute(
                "SELECT lib_name, folder_name FROM core_defs WHERE system_extension = ? ORDER BY lib_name",
                (ext,)
            ).fetchall()
            result[ext] = {
                "name": row["name"],
                "save_exts": row["save_exts"].split(";"),
                "cores": [{"lib": c["lib_name"], "folder": c["folder_name"]} for c in cores]
            }
        return result

    def get_console_folder_names(self) -> dict[str, list[str]]:
        """Return console key → folder name patterns."""
        rows = self._conn.execute("SELECT console_key, folder_name FROM console_folder_names").fetchall()
        result = {}
        for row in rows:
            if row["console_key"] not in result:
                result[row["console_key"]] = []
            result[row["console_key"]].append(row["folder_name"])
        return result

    def get_standalones_for_console(self, console_key: str) -> list[dict]:
        """Return standalone emulator defs for a console."""
        rows = self._conn.execute(
            "SELECT id, label, native_bins, flatpak_id, flatpak_exec, save_dir_template FROM standalone_emulators WHERE console_key = ?",
            (console_key,)
        ).fetchall()
        return [dict(r) for r in rows]


def upsert_console_for_game(
    store: "Store",
    device_id: str,
    console_name: str,
    rom_path: str,
    save_path: str,
    rom_folder_path: str,
) -> None:
    """Infer console folders/emulator from game paths and create-or-update the Console row.

    Called identically from the API (set_game_device) and the CLI (game add) so the
    logic lives in one place.
    """
    emulator = ""
    game_folder = ""
    save_folder = ""
    state_folder = ""

    if save_path:
        save_dir = str(Path(save_path).parent)
        save_folder = save_dir
        emulator = Path(save_dir).name

    if rom_folder_path:
        game_folder = rom_folder_path
    elif rom_path:
        game_folder = str(Path(rom_path).parent.parent)

    if save_folder:
        state_folder = save_folder.replace("saves", "states")

    existing_consoles = store.list_consoles(device_id)
    existing = next(
        (c for c in existing_consoles if c.console_name == console_name and c.device_game_folder == game_folder),
        None,
    )

    if existing:
        existing.device_save_folder = save_folder
        existing.device_state_folder = state_folder
        existing.device_emulator = emulator
        store.set_console(existing)
    else:
        store.set_console(Console(
            id=str(uuid.uuid4()),
            device_id=device_id,
            console_name=console_name,
            shortform_name=console_name.lower()[:4],
            device_game_folder=game_folder,
            device_save_folder=save_folder,
            device_state_folder=state_folder,
            device_emulator=emulator,
        ))
