"""Device CRUD and presence (last_ip / last_seen_at)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from server import arp
from server.store.models import Device

# ensure_device / touch_device run on every authenticated request. Under WAL's
# single-writer model an unconditional UPDATE+commit per request serializes all
# traffic (incl. SSE keepalives and health polls) behind two commits. So both
# only write when something actually changed; last_seen_at is coarse-grained to
# this many seconds, which is well under the 5-min offline threshold in api.py.
_TOUCH_THROTTLE_SECONDS = 30
# Only a device idle this long (the api offline threshold) is merged away, so two
# live instances on one machine (e.g. a dev server with an isolated config) are
# never merged back and forth (#656).
_MERGE_MIN_IDLE_SECONDS = 5 * 60


# Every (table, column) that holds a device id, for merge_devices (#656). Keep in
# sync with schema.py when a table gains a device column.
_DEVICE_REFS = (
    ("consoles", "device_id"), ("game_devices", "device_id"), ("saves", "device_id"),
    ("states", "device_id"), ("locks", "device_id"), ("events", "device_id"),
    ("rom_transfers", "from_device_id"), ("rom_transfers", "to_device_id"),
    ("rom_pull_requests", "from_device_id"), ("rom_pull_requests", "to_device_id"),
    ("switch_mods", "pushed_by"), ("save_sync_baseline", "device_id"),
    ("console_saves", "device_id"), ("console_save_history", "device_id"),
    ("console_save_sync_baseline", "device_id"),
    ("save_conflicts", "winner_device_id"), ("save_conflicts", "loser_device_id"),
    ("console_save_conflicts", "winner_device_id"), ("console_save_conflicts", "loser_device_id"),
)


class DeviceMixin:
    """Operates on `self._conn`; mixed into Store."""

    def ensure_device(self, id: str, name: str) -> tuple[Device, bool]:
        """Register a device if new; update name only if it changed. Idempotent.

        Returns (device, is_new) where is_new is True on first-ever registration.

        A plain SELECT opens no transaction in Python's sqlite3, so the common
        path (known device, unchanged name) does no write — and crucially never
        leaves a write transaction open. `INSERT OR IGNORE` *does* open a
        transaction even when it inserts nothing, so it must always be committed;
        avoiding it on the hot path keeps the WAL writer free.
        """
        row = self._conn.execute("SELECT name FROM devices WHERE id = ?", (id,)).fetchone()
        if row is None:
            # INSERT OR IGNORE (not plain INSERT) so a concurrent first request
            # for the same device can't raise a PK violation.
            self._conn.execute(
                "INSERT OR IGNORE INTO devices (id, name) VALUES (?, ?)", (id, name)
            )
            self._conn.commit()
            return Device(id=id, name=name), True
        if row["name"] != name:
            self._conn.execute("UPDATE devices SET name = ? WHERE id = ?", (name, id))
            self._conn.commit()
        return Device(id=id, name=name), False

    def clear_devices(self) -> None:
        """Remove all devices (forces re-pair). Clears device-referencing rows
        first for the same FK reason as remove_device; per-device game configs
        and saves are re-created when devices reconnect."""
        c = self._conn
        for table in ("game_devices", "consoles", "saves", "states", "locks",
                      "rom_transfers", "rom_pull_requests"):
            c.execute(f"DELETE FROM {table}")
        c.execute("DELETE FROM devices")
        c.commit()

    def list_devices(self) -> list[Device]:
        rows = self._conn.execute(
            "SELECT id, name, last_ip, last_seen_at FROM devices"
        ).fetchall()
        return [Device(**dict(r)) for r in rows]

    def merge_devices(self, old_id: str, new_id: str) -> None:
        """Re-key every row of *old_id* to *new_id*, then drop *old_id*.

        Rows that would collide with one *new_id* already has (UNIQUE/PK) are
        dropped: the surviving device's data wins. *new_id* must already exist,
        so FK checks pass without deferring.
        """
        if old_id == new_id:
            return
        c = self._conn
        for table, col in _DEVICE_REFS:
            c.execute(f"UPDATE OR IGNORE {table} SET {col} = ? WHERE {col} = ?", (new_id, old_id))
            c.execute(f"DELETE FROM {table} WHERE {col} = ?", (old_id,))
        c.execute("DELETE FROM devices WHERE id = ?", (old_id,))
        c.commit()

    def touch_device(self, device_id: str, ip: str) -> list[str]:
        """Record last_ip / last_seen_at / mac, throttled so a busy device doesn't
        commit on every request (see _TOUCH_THROTTLE_SECONDS).

        When the ARP table yields a MAC, any other device row with that MAC is the
        same machine under an older UUID and is merged into this one (#656), provided
        it has been idle past _MERGE_MIN_IDLE_SECONDS.
        Returns the merged-away ids.
        """
        now = datetime.now(timezone.utc)
        row = self._conn.execute(
            "SELECT last_ip, last_seen_at FROM devices WHERE id = ?", (device_id,)
        ).fetchone()
        if row is not None and row["last_ip"] == ip and row["last_seen_at"]:
            try:
                last = datetime.fromisoformat(row["last_seen_at"])
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                if (now - last).total_seconds() < _TOUCH_THROTTLE_SECONDS:
                    return []
            except ValueError:
                pass
        # ponytail: `arp -a` subprocess on non-Linux runs on this throttled path; cache if it shows in profiles
        mac = arp.mac_for_ip(ip)
        self._conn.execute(
            "UPDATE devices SET last_ip = ?, last_seen_at = ?, mac = COALESCE(?, mac) WHERE id = ?",
            (ip, now.isoformat(), mac, device_id),
        )
        self._conn.commit()
        if not mac:
            return []
        cutoff = (now - timedelta(seconds=_MERGE_MIN_IDLE_SECONDS)).isoformat()
        dupes = [r["id"] for r in self._conn.execute(
            "SELECT id FROM devices WHERE mac = ? AND id != ? "
            "AND (last_seen_at IS NULL OR last_seen_at < ?)", (mac, device_id, cutoff)
        )]
        for old in dupes:
            self.merge_devices(old, device_id)
        return dupes

    def remove_device(self, device_id: str) -> None:
        """Remove a device and every row that references it.

        `foreign_keys` is ON for every connection (see connection.py) and the
        referencing tables (game_devices, saves, locks, …) do NOT declare
        `ON DELETE CASCADE`, so deleting the device row directly raises
        `FOREIGN KEY constraint failed` for any device that has configured a
        game or pushed a save. Clear the dependents first, in one transaction.
        """
        c = self._conn
        c.execute("DELETE FROM game_devices WHERE device_id = ?", (device_id,))
        c.execute("DELETE FROM consoles WHERE device_id = ?", (device_id,))
        c.execute("DELETE FROM saves WHERE device_id = ?", (device_id,))
        c.execute("DELETE FROM states WHERE device_id = ?", (device_id,))
        c.execute("DELETE FROM locks WHERE device_id = ?", (device_id,))
        c.execute(
            "DELETE FROM rom_transfers WHERE from_device_id = ? OR to_device_id = ?",
            (device_id, device_id),
        )
        c.execute(
            "DELETE FROM rom_pull_requests WHERE from_device_id = ? OR to_device_id = ?",
            (device_id, device_id),
        )
        # `events` rows are intentionally kept: no FK, they carry their own device_name,
        # and they're bounded by EVENT_LIMIT.
        c.execute("DELETE FROM devices WHERE id = ?", (device_id,))
        c.commit()
