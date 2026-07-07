"""Generic single-value server-wide settings (issue #322).

A small key-value table for server-wide settings that aren't per-game,
per-device, or per-console — currently just the shared SteamGridDB API key,
entered once on the server device and fetched by every connected device
(SteamGridDB has no OAuth/programmatic flow for a per-user key). Kept
generic so a future single server-wide setting doesn't need its own
migration.
"""
from __future__ import annotations

from typing import Optional


class SettingsMixin:
    """Operates on `self._conn`; mixed into Store."""

    def get_setting(self, key: str) -> Optional[str]:
        row = self._conn.execute(
            "SELECT value FROM server_settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO server_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._conn.commit()
