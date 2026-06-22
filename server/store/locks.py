"""Game locks — the duplicate-launch guard with a TTL."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from server.store.models import Lock

LOCK_TTL_HOURS = 4


class LockMixin:
    """Operates on `self._conn`; mixed into Store."""

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

    def release_device_locks(self, device_id: str) -> list[str]:
        """Release every lock held by a device and return the freed game slugs.

        Used when a device is detected offline (issue #238): a crashed device that
        never released its lock would otherwise hold it until the TTL expires.
        """
        rows = self._conn.execute(
            "SELECT game_slug FROM locks WHERE device_id = ?", (device_id,)
        ).fetchall()
        slugs = [row["game_slug"] for row in rows]
        if slugs:
            self._conn.execute("DELETE FROM locks WHERE device_id = ?", (device_id,))
            self._conn.commit()
        return slugs

    def get_lock(self, game_slug: str) -> Optional[Lock]:
        row = self._conn.execute(
            "SELECT game_slug, device_id, acquired_at FROM locks WHERE game_slug = ?",
            (game_slug,),
        ).fetchone()
        return Lock(**dict(row)) if row else None
