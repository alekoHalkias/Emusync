"""Save-conflict records — the central log behind the GUI Conflicts panel (#243).

`emusync run` auto-resolves a true save divergence (both copies changed since the
last sync) newest-wins. It reports the resolution here so any device's GUI can see
it and offer to recover the losing copy. Rows are `open` until dismissed.

console_save_conflicts (#482) is the console-scoped equivalent for shared-memcard
consoles (PS2/DC/GC/PSP/3DS) — save_conflicts.game_slug is a hard FK to games(slug),
so a divergence on a console-wide card (no game row backs it) has nowhere to go
there. list_open_conflicts merges both into one list so the GUI keeps polling a
single endpoint.
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

    def add_console_conflict(
        self,
        console_key: str,
        winner_device_id: str,
        loser_device_id: str,
        winner_hash: str,
        loser_hash: str,
    ) -> dict:
        """Console-key equivalent of add_conflict, same dedup rule (#482)."""
        existing = self._conn.execute(
            """SELECT id FROM console_save_conflicts
               WHERE console_key = ? AND status = 'open'
                 AND winner_hash = ? AND loser_hash = ?""",
            (console_key, winner_hash, loser_hash),
        ).fetchone()
        now = datetime.now(timezone.utc).isoformat()
        if existing:
            cid = existing["id"]
        else:
            cid = str(uuid.uuid4())
            self._conn.execute(
                """INSERT INTO console_save_conflicts
                   (id, console_key, winner_device_id, loser_device_id, winner_hash, loser_hash, resolved_at, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'open')""",
                (cid, console_key, winner_device_id, loser_device_id, winner_hash, loser_hash, now),
            )
            self._conn.commit()
        return {"id": cid, "resolved_at": now}

    def list_open_conflicts(self) -> list[dict]:
        """Open conflicts across all games AND shared-memcard consoles, newest
        first, with game/console + device names (#482). game_name/console_key
        are null on whichever side a row doesn't apply to — the GUI branches on
        which one is set to tell the two kinds apart."""
        rows = self._conn.execute(
            """SELECT c.id, c.game_slug, g.name AS game_name, NULL AS console_key,
                      c.winner_device_id, c.loser_device_id,
                      c.winner_hash, c.loser_hash, c.resolved_at,
                      wd.name AS winner_device_name, ld.name AS loser_device_name
               FROM save_conflicts c
               JOIN games g          ON g.slug = c.game_slug
               LEFT JOIN devices wd  ON wd.id = c.winner_device_id
               LEFT JOIN devices ld  ON ld.id = c.loser_device_id
               WHERE c.status = 'open'
               UNION ALL
               SELECT c.id, NULL AS game_slug, NULL AS game_name, c.console_key,
                      c.winner_device_id, c.loser_device_id,
                      c.winner_hash, c.loser_hash, c.resolved_at,
                      wd.name AS winner_device_name, ld.name AS loser_device_name
               FROM console_save_conflicts c
               LEFT JOIN devices wd  ON wd.id = c.winner_device_id
               LEFT JOIN devices ld  ON ld.id = c.loser_device_id
               WHERE c.status = 'open'
               ORDER BY resolved_at DESC""",
        ).fetchall()
        return [dict(r) for r in rows]

    def dismiss_conflict(self, conflict_id: str) -> bool:
        """Mark a conflict dismissed — tries the per-game table first, then the
        console-scoped one (#482); ids are UUIDs, globally unique either way, so
        at most one of the two ever matches. Returns False if it didn't exist
        (or already was) in either."""
        cur = self._conn.execute(
            "UPDATE save_conflicts SET status = 'dismissed' WHERE id = ? AND status = 'open'",
            (conflict_id,),
        )
        if cur.rowcount > 0:
            self._conn.commit()
            return True
        cur = self._conn.execute(
            "UPDATE console_save_conflicts SET status = 'dismissed' WHERE id = ? AND status = 'open'",
            (conflict_id,),
        )
        self._conn.commit()
        return cur.rowcount > 0
