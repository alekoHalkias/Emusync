"""Game CRUD (`games`) and per-device game configuration (`game_devices`)."""
from __future__ import annotations

from typing import Optional

from server.store.models import Game, GameDevice


class GameMixin:
    """Operates on `self._conn`; mixed into Store."""

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


class GameDeviceMixin:
    """Operates on `self._conn`; mixed into Store."""

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

    def games_overview(self, device_id: str) -> list[dict]:
        """Everything the game list needs for one device, in a single query.

        Collapses the renderer's old per-game fan-out (getSaveMeta + getLock +
        getGameDevice for every game) into one round-trip. Each referenced table
        has at most one matching row per game — locks PK is game_slug, saves is
        delete-then-insert (one row/slug), game_devices PK is (slug, device_id) —
        so the LEFT JOINs never fan out.
        """
        rows = self._conn.execute(
            """SELECT g.slug, g.name, g.console,
                      l.device_id      AS lock_device_id,
                      s.pushed_at      AS last_push,
                      gd.rom_path, gd.save_path, gd.state_path,
                      gd.launch_command, gd.rom_folder_path,
                      (gd.game_slug IS NOT NULL) AS is_local
               FROM games g
               LEFT JOIN locks l        ON l.game_slug = g.slug
               LEFT JOIN saves s        ON s.game_slug = g.slug
               LEFT JOIN game_devices gd ON gd.game_slug = g.slug AND gd.device_id = ?
               ORDER BY g.name""",
            (device_id,),
        ).fetchall()
        result = []
        for r in rows:
            result.append({
                "slug": r["slug"],
                "name": r["name"],
                "console": r["console"],
                "locked": r["lock_device_id"] is not None,
                "lock_device_id": r["lock_device_id"],
                "last_push": r["last_push"],
                "is_local": bool(r["is_local"]),
                "rom_path": r["rom_path"] or "",
                "save_path": r["save_path"] or "",
                "state_path": r["state_path"] or "",
                "launch_command": r["launch_command"] or "",
                "rom_folder_path": r["rom_folder_path"] or "",
            })
        return result

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
