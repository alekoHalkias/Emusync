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

    def update_game_sgdb_id(self, slug: str, sgdb_game_id: Optional[int]) -> None:
        """Remember a manually-picked SteamGridDB game match (issue #325), shared
        across every device via this same server-side row."""
        self._conn.execute(
            "UPDATE games SET sgdb_game_id = ? WHERE slug = ?", (sgdb_game_id, slug)
        )
        self._conn.commit()

    def remove_game(self, slug: str) -> None:
        # Drop on-disk save/state blobs first; the rows go via FK cascade, but the
        # files would otherwise be orphaned (issue #239).
        self.delete_blobs_for_game(slug)
        self._conn.execute("DELETE FROM games WHERE slug = ?", (slug,))
        self._conn.commit()

    def list_games(self) -> list[Game]:
        rows = self._conn.execute("SELECT slug, name, console, sgdb_game_id FROM games").fetchall()
        return [Game(**dict(r)) for r in rows]

    def get_game(self, slug: str) -> Optional[Game]:
        row = self._conn.execute(
            "SELECT slug, name, console, sgdb_game_id FROM games WHERE slug = ?", (slug,)
        ).fetchone()
        return Game(**dict(row)) if row else None


class GameDeviceMixin:
    """Operates on `self._conn`; mixed into Store."""

    def set_game_device(self, gd: GameDevice) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO game_devices
               (game_slug, device_id, rom_path, save_path, launch_command, state_path, rom_folder_path,
                rom_source, rom_rel_path, local_rom_path, rom_sha256)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (gd.game_slug, gd.device_id, gd.rom_path, gd.save_path, gd.launch_command,
             gd.state_path, gd.rom_folder_path, gd.rom_source, gd.rom_rel_path,
             gd.local_rom_path, gd.rom_sha256),
        )
        self._conn.commit()

    def get_game_device(self, game_slug: str, device_id: str) -> Optional[GameDevice]:
        row = self._conn.execute(
            """SELECT game_slug, device_id, rom_path, save_path, launch_command, state_path,
                      rom_folder_path, rom_source, rom_rel_path, local_rom_path, rom_sha256
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

    def get_network_source_for_game(self, game_slug: str) -> Optional[dict]:
        """A network-sourced config for *game_slug* on any device (issue #270).

        Lets a device that doesn't have the game set up reach the same NAS: it
        joins the returned ``rom_rel_path`` to its own mount root. Returns the
        most recently-updated network row's portable bits (rel-path, console,
        a launch-command template + the source device's rom/save/state paths so
        the receiver can rewrite them), or None if no device has it on a share.
        """
        row = self._conn.execute(
            """SELECT g.console, gd.device_id, d.name AS device_name,
                      gd.rom_path, gd.rom_rel_path, gd.launch_command,
                      gd.save_path, gd.state_path, gd.rom_folder_path
               FROM game_devices gd
               JOIN games g   ON g.slug = gd.game_slug
               JOIN devices d ON d.id = gd.device_id
               WHERE gd.game_slug = ? AND gd.rom_source = 'network'
                     AND gd.rom_rel_path != ''
               ORDER BY gd.rowid DESC LIMIT 1""",
            (game_slug,),
        ).fetchone()
        return dict(row) if row else None

    def games_overview(self, device_id: str) -> list[dict]:
        """Everything the game list needs for one device, in a single query.

        Collapses the renderer's old per-game fan-out (getSaveMeta + getLock +
        getGameDevice for every game) into one round-trip. `locks` (PK game_slug)
        and `game_devices` (PK (slug, device_id), filtered to this device) each
        match at most one row per game, so those LEFT JOINs never fan out. `saves`
        does NOT — it keeps history (many generations per game, issue #7), so
        joining it would emit one row per generation and duplicate the game in the
        list once a game has been played more than once (issue #249). The only
        column needed from it is `last_push`, so it's a correlated subquery picking
        the newest generation (rowid DESC = the current blob, matching blobs.py).
        """
        rows = self._conn.execute(
            """SELECT g.slug, g.name, g.console,
                      l.device_id      AS lock_device_id,
                      (SELECT s.pushed_at FROM saves s
                         WHERE s.game_slug = g.slug
                         ORDER BY s.rowid DESC LIMIT 1) AS last_push,
                      gd.rom_path, gd.save_path, gd.state_path,
                      gd.launch_command, gd.rom_folder_path,
                      gd.rom_source, gd.rom_rel_path, gd.local_rom_path,
                      (gd.game_slug IS NOT NULL) AS is_local
               FROM games g
               LEFT JOIN locks l        ON l.game_slug = g.slug
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
                "rom_source": r["rom_source"] or "local",
                "rom_rel_path": r["rom_rel_path"] or "",
                "local_rom_path": r["local_rom_path"] or "",
            })
        return result

    def list_game_devices_for_device(self, device_id: str) -> list[dict]:
        rows = self._conn.execute(
            """SELECT g.slug, g.name, g.console, gd.rom_path, gd.save_path,
                      gd.launch_command, gd.state_path, gd.rom_folder_path,
                      gd.rom_source, gd.rom_rel_path, gd.local_rom_path
               FROM game_devices gd
               JOIN games g ON g.slug = gd.game_slug
               WHERE gd.device_id = ?
               ORDER BY g.name""",
            (device_id,),
        ).fetchall()
        return [dict(r) for r in rows]
