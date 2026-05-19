import hashlib
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

LOCK_EXPIRE_SECONDS = 4 * 3600


@dataclass
class Device:
    id: str
    name: str
    token: str
    created_at: int


@dataclass
class Game:
    slug: str
    name: str
    created_at: int


@dataclass
class GameDevice:
    game_slug: str
    device_id: str
    rom_path: str = ""
    save_path: str = ""
    launch_command: str = ""


@dataclass
class SaveMeta:
    game_slug: str
    device_id: str
    sha256: str
    size: int
    created_at: int


@dataclass
class Lock:
    game_slug: str
    device_id: str
    acquired_at: int


class Store:
    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.data_dir / "emusync.db"
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._migrate()

    def _migrate(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS devices (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                token       TEXT NOT NULL UNIQUE,
                created_at  INTEGER DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS games (
                slug        TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                created_at  INTEGER DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS game_devices (
                game_slug       TEXT NOT NULL,
                device_id       TEXT NOT NULL,
                rom_path        TEXT DEFAULT '',
                save_path       TEXT DEFAULT '',
                launch_command  TEXT DEFAULT '',
                PRIMARY KEY (game_slug, device_id)
            );

            CREATE TABLE IF NOT EXISTS saves (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                game_slug   TEXT NOT NULL,
                device_id   TEXT NOT NULL,
                sha256      TEXT NOT NULL,
                data        BLOB NOT NULL,
                size        INTEGER NOT NULL,
                created_at  INTEGER DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS locks (
                game_slug   TEXT PRIMARY KEY,
                device_id   TEXT NOT NULL,
                acquired_at INTEGER DEFAULT (strftime('%s','now'))
            );
        """)
        self.conn.commit()

    # ── Devices ────────────────────────────────────────────────────────────

    def register_device(self, device_id: str, name: str, token: str) -> Device:
        self.conn.execute(
            "INSERT OR REPLACE INTO devices (id, name, token) VALUES (?, ?, ?)",
            (device_id, name, token),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
        return Device(**dict(row))

    def device_by_token(self, token: str) -> Optional[Device]:
        row = self.conn.execute("SELECT * FROM devices WHERE token = ?", (token,)).fetchone()
        return Device(**dict(row)) if row else None

    def list_devices(self) -> List[Device]:
        rows = self.conn.execute("SELECT * FROM devices ORDER BY created_at").fetchall()
        return [Device(**dict(r)) for r in rows]

    # ── Games ──────────────────────────────────────────────────────────────

    def add_game(self, slug: str, name: str) -> Game:
        self.conn.execute(
            "INSERT OR IGNORE INTO games (slug, name) VALUES (?, ?)",
            (slug, name),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM games WHERE slug = ?", (slug,)).fetchone()
        return Game(**dict(row))

    def remove_game(self, slug: str):
        for table in ("saves", "locks", "game_devices", "games"):
            col = "game_slug" if table != "games" else "slug"
            self.conn.execute(f"DELETE FROM {table} WHERE {col} = ?", (slug,))
        self.conn.commit()

    def list_games(self) -> List[Game]:
        rows = self.conn.execute("SELECT * FROM games ORDER BY created_at DESC").fetchall()
        return [Game(**dict(r)) for r in rows]

    def get_game(self, slug: str) -> Optional[Game]:
        row = self.conn.execute("SELECT * FROM games WHERE slug = ?", (slug,)).fetchone()
        return Game(**dict(row)) if row else None

    def update_game_name(self, slug: str, name: str):
        self.conn.execute("UPDATE games SET name = ? WHERE slug = ?", (name, slug))
        self.conn.commit()

    # ── Game-device config ─────────────────────────────────────────────────

    def set_game_device(self, gd: GameDevice):
        self.conn.execute(
            """
            INSERT INTO game_devices (game_slug, device_id, rom_path, save_path, launch_command)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(game_slug, device_id) DO UPDATE SET
                rom_path       = excluded.rom_path,
                save_path      = excluded.save_path,
                launch_command = excluded.launch_command
            """,
            (gd.game_slug, gd.device_id, gd.rom_path, gd.save_path, gd.launch_command),
        )
        self.conn.commit()

    def get_game_device(self, game_slug: str, device_id: str) -> Optional[GameDevice]:
        row = self.conn.execute(
            "SELECT * FROM game_devices WHERE game_slug = ? AND device_id = ?",
            (game_slug, device_id),
        ).fetchone()
        return GameDevice(**dict(row)) if row else None

    # ── Saves ──────────────────────────────────────────────────────────────

    def push_save(self, game_slug: str, device_id: str, data: bytes) -> SaveMeta:
        sha256 = hashlib.sha256(data).hexdigest()
        self.conn.execute(
            "INSERT INTO saves (game_slug, device_id, sha256, data, size) VALUES (?, ?, ?, ?, ?)",
            (game_slug, device_id, sha256, data, len(data)),
        )
        self.conn.commit()
        return self.get_save_meta(game_slug)  # type: ignore

    def pull_save(self, game_slug: str) -> Tuple[Optional[bytes], Optional[SaveMeta]]:
        row = self.conn.execute(
            "SELECT * FROM saves WHERE game_slug = ? ORDER BY id DESC LIMIT 1",
            (game_slug,),
        ).fetchone()
        if not row:
            return None, None
        meta = SaveMeta(
            game_slug=row["game_slug"],
            device_id=row["device_id"],
            sha256=row["sha256"],
            size=row["size"],
            created_at=row["created_at"],
        )
        return bytes(row["data"]), meta

    def get_save_meta(self, game_slug: str) -> Optional[SaveMeta]:
        row = self.conn.execute(
            "SELECT game_slug, device_id, sha256, size, created_at FROM saves "
            "WHERE game_slug = ? ORDER BY id DESC LIMIT 1",
            (game_slug,),
        ).fetchone()
        return SaveMeta(**dict(row)) if row else None

    # ── Locks ──────────────────────────────────────────────────────────────

    def acquire_lock(self, game_slug: str, device_id: str):
        stale = int(time.time()) - LOCK_EXPIRE_SECONDS
        self.conn.execute(
            "DELETE FROM locks WHERE game_slug = ? AND acquired_at < ?",
            (game_slug, stale),
        )
        self.conn.commit()

        row = self.conn.execute("SELECT * FROM locks WHERE game_slug = ?", (game_slug,)).fetchone()
        if row and row["device_id"] != device_id:
            raise ValueError(f"Locked by device {row['device_id']}")

        self.conn.execute(
            "INSERT OR REPLACE INTO locks (game_slug, device_id, acquired_at) VALUES (?, ?, ?)",
            (game_slug, device_id, int(time.time())),
        )
        self.conn.commit()

    def release_lock(self, game_slug: str, device_id: str):
        self.conn.execute(
            "DELETE FROM locks WHERE game_slug = ? AND device_id = ?",
            (game_slug, device_id),
        )
        self.conn.commit()

    def get_lock(self, game_slug: str) -> Optional[Lock]:
        row = self.conn.execute("SELECT * FROM locks WHERE game_slug = ?", (game_slug,)).fetchone()
        return Lock(**dict(row)) if row else None
