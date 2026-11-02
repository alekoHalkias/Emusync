"""Game locks — the duplicate-launch guard with a TTL."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from server.store.models import Lock

LOCK_TTL_HOURS = 4


def _lock_cutoff() -> str:
    """ISO timestamp before which a lock is expired. Locks are stored as UTC
    isoformat strings, so plain string comparison orders them (#734)."""
    return (datetime.now(timezone.utc) - timedelta(hours=LOCK_TTL_HOURS)).isoformat()


class LockMixin:
    """Operates on `self._conn`; mixed into Store."""

    def acquire_lock(self, game_slug: str, device_id: str) -> None:
        """Take or refresh the lock in one statement so two devices racing for a
        free (or expired) lock can't both win (#734). The holder refreshes its own
        lock; anyone may take it once it is older than LOCK_TTL_HOURS."""
        self._conn.execute(
            "INSERT INTO locks (game_slug, device_id, acquired_at) VALUES (?, ?, ?) "
            "ON CONFLICT(game_slug) DO UPDATE SET device_id = excluded.device_id, "
            "acquired_at = excluded.acquired_at "
            "WHERE locks.device_id = excluded.device_id OR locks.acquired_at < ?",
            (game_slug, device_id, datetime.now(timezone.utc).isoformat(), _lock_cutoff()),
        )
        self._conn.commit()
        holder = self._conn.execute(
            "SELECT device_id FROM locks WHERE game_slug = ?", (game_slug,)
        ).fetchone()
        if holder and holder["device_id"] != device_id:
            raise ValueError(f"Game is locked by device {holder['device_id']}")

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
            "SELECT game_slug, device_id, acquired_at FROM locks "
            "WHERE game_slug = ? AND acquired_at >= ?",
            (game_slug, _lock_cutoff()),
        ).fetchone()
        return Lock(**dict(row)) if row else None
