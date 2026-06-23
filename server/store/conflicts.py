"""Save-conflict records — the central log behind the GUI Conflicts panel (#243).

`emusync run` auto-resolves a true save divergence (both copies changed since the
last sync) newest-wins. It reports the resolution here so any device's GUI can see
it and offer to recover the losing copy. Rows are `open` until dismissed.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional


class ConflictMixin:
    """Operates on `self._conn`; mixed into Store."""

    def add_conflict(
        self,
        game_slug: str,
        winner_device_id: str,
        loser_device_id: str,
        winner_hash: str,
        loser_hash: str,
    ) -> dict:
        """Record an auto-resolved divergence. Deduped: if an open conflict with the
        same winner/loser hashes already exists for this game, it's returned as-is
        (a re-launch reporting the same resolution shouldn't pile up rows)."""
        existing = self._conn.execute(
            """SELECT id FROM save_conflicts
               WHERE game_slug = ? AND status = 'open'
                 AND winner_hash = ? AND loser_hash = ?""",
            (game_slug, winner_hash, loser_hash),
        ).fetchone()
        now = datetime.now(timezone.utc).isoformat()
        if existing:
            cid = existing["id"]
        else:
            cid = str(uuid.uuid4())
            self._conn.execute(
                """INSERT INTO save_conflicts
                   (id, game_slug, winner_device_id, loser_device_id, winner_hash, loser_hash, resolved_at, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'open')""",
                (cid, game_slug, winner_device_id, loser_device_id, winner_hash, loser_hash, now),
            )
            self._conn.commit()
        return {"id": cid, "resolved_at": now}

    def list_open_conflicts(self) -> list[dict]:
        """Open conflicts across all games, newest first, with game + device names."""
        rows = self._conn.execute(
            """SELECT c.id, c.game_slug, g.name AS game_name,
                      c.winner_device_id, c.loser_device_id,
                      c.winner_hash, c.loser_hash, c.resolved_at,
                      wd.name AS winner_device_name, ld.name AS loser_device_name
               FROM save_conflicts c
               JOIN games g          ON g.slug = c.game_slug
               LEFT JOIN devices wd  ON wd.id = c.winner_device_id
               LEFT JOIN devices ld  ON ld.id = c.loser_device_id
               WHERE c.status = 'open'
               ORDER BY c.resolved_at DESC""",
        ).fetchall()
        return [dict(r) for r in rows]

    def dismiss_conflict(self, conflict_id: str) -> bool:
        """Mark a conflict dismissed. Returns False if it didn't exist (or already was)."""
        cur = self._conn.execute(
            "UPDATE save_conflicts SET status = 'dismissed' WHERE id = ? AND status = 'open'",
            (conflict_id,),
        )
        self._conn.commit()
        return cur.rowcount > 0
