"""Device CRUD and presence (last_ip / last_seen_at)."""
from __future__ import annotations

from datetime import datetime, timezone

from server.store.models import Device


class DeviceMixin:
    """Operates on `self._conn`; mixed into Store."""

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
