from __future__ import annotations

import hashlib
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

LOCK_TTL_HOURS = 4

_SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    id   TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    token TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS games (
    slug TEXT PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS game_devices (
    game_slug      TEXT NOT NULL REFERENCES games(slug) ON DELETE CASCADE,
    device_id      TEXT NOT NULL REFERENCES devices(id),
    rom_path       TEXT NOT NULL DEFAULT '',
    save_path      TEXT NOT NULL DEFAULT '',
    launch_command TEXT NOT NULL DEFAULT '',
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
CREATE TABLE IF NOT EXISTS locks (
    game_slug   TEXT PRIMARY KEY REFERENCES games(slug) ON DELETE CASCADE,
    device_id   TEXT NOT NULL REFERENCES devices(id),
    acquired_at TEXT NOT NULL
);
"""


@dataclass
class Device:
    id: str
    name: str
    token: str


@dataclass
class Game:
    slug: str
    name: str


@dataclass
class GameDevice:
    game_slug: str
    device_id: str
    rom_path: str
    save_path: str
    launch_command: str


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
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ── devices ──────────────────────────────────────────────────────────────

    def register_device(self, id: str, name: str, token: str) -> Device:
        self._conn.execute(
            "INSERT OR REPLACE INTO devices (id, name, token) VALUES (?, ?, ?)",
            (id, name, token),
        )
        self._conn.commit()
        return Device(id=id, name=name, token=token)

    def clear_devices(self) -> None:
        self._conn.execute("DELETE FROM devices")
        self._conn.commit()

    def device_by_token(self, token: str) -> Optional[Device]:
        row = self._conn.execute(
            "SELECT id, name, token FROM devices WHERE token = ?", (token,)
        ).fetchone()
        return Device(**dict(row)) if row else None

    def list_devices(self) -> list[Device]:
        rows = self._conn.execute("SELECT id, name, token FROM devices").fetchall()
        return [Device(**dict(r)) for r in rows]

    # ── games ─────────────────────────────────────────────────────────────────

    def add_game(self, slug: str, name: str) -> Game:
        self._conn.execute(
            "INSERT OR REPLACE INTO games (slug, name) VALUES (?, ?)", (slug, name)
        )
        self._conn.commit()
        return Game(slug=slug, name=name)

    def remove_game(self, slug: str) -> None:
        self._conn.execute("DELETE FROM games WHERE slug = ?", (slug,))
        self._conn.commit()

    def list_games(self) -> list[Game]:
        rows = self._conn.execute("SELECT slug, name FROM games").fetchall()
        return [Game(**dict(r)) for r in rows]

    def get_game(self, slug: str) -> Optional[Game]:
        row = self._conn.execute(
            "SELECT slug, name FROM games WHERE slug = ?", (slug,)
        ).fetchone()
        return Game(**dict(row)) if row else None

    # ── game_devices ──────────────────────────────────────────────────────────

    def set_game_device(self, gd: GameDevice) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO game_devices
               (game_slug, device_id, rom_path, save_path, launch_command)
               VALUES (?, ?, ?, ?, ?)""",
            (gd.game_slug, gd.device_id, gd.rom_path, gd.save_path, gd.launch_command),
        )
        self._conn.commit()

    def get_game_device(self, game_slug: str, device_id: str) -> Optional[GameDevice]:
        row = self._conn.execute(
            """SELECT game_slug, device_id, rom_path, save_path, launch_command
               FROM game_devices WHERE game_slug = ? AND device_id = ?""",
            (game_slug, device_id),
        ).fetchone()
        return GameDevice(**dict(row)) if row else None

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

    def get_lock(self, game_slug: str) -> Optional[Lock]:
        row = self._conn.execute(
            "SELECT game_slug, device_id, acquired_at FROM locks WHERE game_slug = ?",
            (game_slug,),
        ).fetchone()
        return Lock(**dict(row)) if row else None
