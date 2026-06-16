"""Save and state blob storage.

Saves and states share identical storage, so private blob helpers parameterised
by table name back the public save/state methods.

Each push keeps the previous generations (up to ``HISTORY_LIMIT`` per game) instead
of overwriting, so a bad sync can be rolled back (issue #7). The *current* blob is
simply the most recently inserted row (ordered by SQLite ``rowid``, which is
monotonic for inserts and so unambiguous even when two pushes share a timestamp).
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional

from server.store.models import SaveMeta

# How many generations to retain per game, per blob table. Older rows are pruned
# on every push. Saves/states are small (KBs), so this is generous.
HISTORY_LIMIT = 20


class SaveStateMixin:
    """Operates on `self._conn`; mixed into Store."""

    # ── shared private helpers ─────────────────────────────────────────────────

    def _push_blob(self, table: str, game_slug: str, device_id: str, data: bytes) -> SaveMeta:
        h = hashlib.sha256(data).hexdigest()
        now = datetime.now(timezone.utc).isoformat()
        # Dedupe: if the current (newest) blob already has this exact content, don't
        # create another history generation — return the existing one unchanged.
        current = self._conn.execute(
            f"SELECT device_id, hash, pushed_at FROM {table} WHERE game_slug = ? ORDER BY rowid DESC LIMIT 1",
            (game_slug,),
        ).fetchone()
        if current and current["hash"] == h:
            return SaveMeta(
                game_slug=game_slug, device_id=current["device_id"],
                hash=current["hash"], pushed_at=current["pushed_at"], size=len(data),
            )
        self._conn.execute(
            f"INSERT INTO {table} (id, game_slug, device_id, data, hash, pushed_at) VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), game_slug, device_id, data, h, now),
        )
        self._prune_history(table, game_slug)
        self._conn.commit()
        return SaveMeta(game_slug=game_slug, device_id=device_id, hash=h, pushed_at=now, size=len(data))

    def _prune_history(self, table: str, game_slug: str) -> None:
        """Delete all but the newest HISTORY_LIMIT generations for a game."""
        self._conn.execute(
            f"""DELETE FROM {table}
                WHERE game_slug = ? AND rowid NOT IN (
                    SELECT rowid FROM {table} WHERE game_slug = ? ORDER BY rowid DESC LIMIT ?
                )""",
            (game_slug, game_slug, HISTORY_LIMIT),
        )

    def _pull_blob(self, table: str, game_slug: str) -> tuple[Optional[bytes], Optional[SaveMeta]]:
        # The current blob is the most recently inserted row for this game.
        row = self._conn.execute(
            f"SELECT data, game_slug, device_id, hash, pushed_at FROM {table} WHERE game_slug = ? ORDER BY rowid DESC LIMIT 1",
            (game_slug,),
        ).fetchone()
        if not row:
            return None, None
        meta = SaveMeta(
            game_slug=row["game_slug"],
            device_id=row["device_id"],
            hash=row["hash"],
            pushed_at=row["pushed_at"],
            size=len(row["data"]),
        )
        return bytes(row["data"]), meta

    def _get_blob_meta(self, table: str, game_slug: str) -> Optional[SaveMeta]:
        row = self._conn.execute(
            f"SELECT game_slug, device_id, hash, pushed_at, length(data) AS size FROM {table} WHERE game_slug = ? ORDER BY rowid DESC LIMIT 1",
            (game_slug,),
        ).fetchone()
        return SaveMeta(**dict(row)) if row else None

    def _list_blob_history(self, table: str, game_slug: str) -> list[dict]:
        """Return every retained generation for a game, newest first."""
        rows = self._conn.execute(
            f"""SELECT id, device_id, hash, pushed_at, length(data) AS size
                FROM {table} WHERE game_slug = ? ORDER BY rowid DESC""",
            (game_slug,),
        ).fetchall()
        return [dict(r) for r in rows]

    def _restore_blob(self, table: str, game_slug: str, version_id: str) -> Optional[SaveMeta]:
        """Make a past generation current by re-inserting its bytes as a new row.

        Restoring never destroys history: the chosen version's content is pushed as
        a fresh generation (subject to the same dedupe + prune rules), so the
        timeline keeps growing forward. Returns None if the version doesn't exist
        for this game.
        """
        row = self._conn.execute(
            f"SELECT device_id, data FROM {table} WHERE id = ? AND game_slug = ?",
            (version_id, game_slug),
        ).fetchone()
        if not row:
            return None
        return self._push_blob(table, game_slug, row["device_id"], bytes(row["data"]))

    # ── saves ─────────────────────────────────────────────────────────────────

    def push_save(self, game_slug: str, device_id: str, data: bytes) -> SaveMeta:
        return self._push_blob("saves", game_slug, device_id, data)

    def pull_save(self, game_slug: str) -> tuple[Optional[bytes], Optional[SaveMeta]]:
        return self._pull_blob("saves", game_slug)

    def get_save_meta(self, game_slug: str) -> Optional[SaveMeta]:
        return self._get_blob_meta("saves", game_slug)

    def list_save_history(self, game_slug: str) -> list[dict]:
        return self._list_blob_history("saves", game_slug)

    def restore_save(self, game_slug: str, version_id: str) -> Optional[SaveMeta]:
        return self._restore_blob("saves", game_slug, version_id)

    # ── states ─────────────────────────────────────────────────────────────────

    def push_state(self, game_slug: str, device_id: str, data: bytes) -> SaveMeta:
        return self._push_blob("states", game_slug, device_id, data)

    def pull_state(self, game_slug: str) -> tuple[Optional[bytes], Optional[SaveMeta]]:
        return self._pull_blob("states", game_slug)

    def get_state_meta(self, game_slug: str) -> Optional[SaveMeta]:
        return self._get_blob_meta("states", game_slug)

    def list_state_history(self, game_slug: str) -> list[dict]:
        return self._list_blob_history("states", game_slug)

    def restore_state(self, game_slug: str, version_id: str) -> Optional[SaveMeta]:
        return self._restore_blob("states", game_slug, version_id)
