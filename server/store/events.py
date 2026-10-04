"""Event log (device connect/disconnect, server lifecycle, etc.)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


EVENT_LIMIT = 1000  # newest rows kept; older ones are pruned on every write


class EventMixin:
    """Operates on `self._conn`; mixed into Store."""

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
        # ids are autoincrement, so "newest EVENT_LIMIT" is a plain id cutoff
        self._conn.execute("DELETE FROM events WHERE id <= (SELECT MAX(id) FROM events) - ?", (EVENT_LIMIT,))
        self._conn.commit()

    def list_events(self, limit: int = 100) -> list[dict]:
        rows = self._conn.execute(
            "SELECT type, game_slug, device_id, device_name, rom_path, occurred_at FROM events ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
