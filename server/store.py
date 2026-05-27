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
_SCHEMA_VERSION = 2

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
"""


def _try(conn: sqlite3.Connection, sql: str) -> None:
    """Execute a DDL statement, silently ignoring OperationalError (already exists / column missing)."""
    try:
        conn.execute(sql)
    except sqlite3.OperationalError:
        pass


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
            """SELECT d.id, d.name, gd.rom_path, gd.save_path, gd.state_path
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
            }
            for row in rows
        ]

    # ── saves ─────────────────────────────────────────────────────────────────

    def push_save(self, game_slug: str, device_id: str, data: bytes) -> SaveMeta:
        h = hashlib.sha256(data).hexdigest()
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute("DELETE FROM saves WHERE game_slug = ?", (game_slug,))
        self._conn.execute(
            "INSERT INTO saves (id, game_slug, device_id, data, hash, pushed_at) VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), game_slug, device_id, data, h, now),
        )
        self._conn.commit()
        return SaveMeta(game_slug=game_slug, device_id=device_id, hash=h, pushed_at=now)

    def pull_save(self, game_slug: str) -> tuple[Optional[bytes], Optional[SaveMeta]]:
        row = self._conn.execute(
            "SELECT data, game_slug, device_id, hash, pushed_at FROM saves WHERE game_slug = ? ORDER BY pushed_at DESC LIMIT 1",
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

    def get_save_meta(self, game_slug: str) -> Optional[SaveMeta]:
        row = self._conn.execute(
            "SELECT game_slug, device_id, hash, pushed_at FROM saves WHERE game_slug = ? ORDER BY pushed_at DESC LIMIT 1",
            (game_slug,),
        ).fetchone()
        return SaveMeta(**dict(row)) if row else None

    # ── states ─────────────────────────────────────────────────────────────────

    def push_state(self, game_slug: str, device_id: str, data: bytes) -> SaveMeta:
        h = hashlib.sha256(data).hexdigest()
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute("DELETE FROM states WHERE game_slug = ?", (game_slug,))
        self._conn.execute(
            "INSERT INTO states (id, game_slug, device_id, data, hash, pushed_at) VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), game_slug, device_id, data, h, now),
        )
        self._conn.commit()
        return SaveMeta(game_slug=game_slug, device_id=device_id, hash=h, pushed_at=now)

    def pull_state(self, game_slug: str) -> tuple[Optional[bytes], Optional[SaveMeta]]:
        row = self._conn.execute(
            "SELECT data, game_slug, device_id, hash, pushed_at FROM states WHERE game_slug = ? ORDER BY pushed_at DESC LIMIT 1",
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

    def get_state_meta(self, game_slug: str) -> Optional[SaveMeta]:
        row = self._conn.execute(
            "SELECT game_slug, device_id, hash, pushed_at FROM states WHERE game_slug = ? ORDER BY pushed_at DESC LIMIT 1",
            (game_slug,),
        ).fetchone()
        return SaveMeta(**dict(row)) if row else None

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
