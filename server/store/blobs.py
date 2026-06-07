"""Save and state blob storage.

Saves and states share identical storage, so private blob helpers parameterised
by table name back the public save/state methods.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional

from server.store.models import SaveMeta


class SaveStateMixin:
    """Operates on `self._conn`; mixed into Store."""

    # ── shared private helpers ─────────────────────────────────────────────────

    def _push_blob(self, table: str, game_slug: str, device_id: str, data: bytes) -> SaveMeta:
        h = hashlib.sha256(data).hexdigest()
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(f"DELETE FROM {table} WHERE game_slug = ?", (game_slug,))
        self._conn.execute(
            f"INSERT INTO {table} (id, game_slug, device_id, data, hash, pushed_at) VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), game_slug, device_id, data, h, now),
        )
        self._conn.commit()
        return SaveMeta(game_slug=game_slug, device_id=device_id, hash=h, pushed_at=now)

    def _pull_blob(self, table: str, game_slug: str) -> tuple[Optional[bytes], Optional[SaveMeta]]:
        # _push_blob deletes-then-inserts, so a slug has at most one row.
        row = self._conn.execute(
            f"SELECT data, game_slug, device_id, hash, pushed_at FROM {table} WHERE game_slug = ? LIMIT 1",
            (game_slug,),
        ).fetchone()
        if not row:
            return None, None
        meta = SaveMeta(
            game_slug=row["game_slug"],
            device_id=row["device_id"],
            hash=row["hash"],
            pushed_at=row["pushed_at"],
        )
        return bytes(row["data"]), meta

    def _get_blob_meta(self, table: str, game_slug: str) -> Optional[SaveMeta]:
        # _push_blob deletes-then-inserts, so a slug has at most one row.
        row = self._conn.execute(
            f"SELECT game_slug, device_id, hash, pushed_at FROM {table} WHERE game_slug = ? LIMIT 1",
            (game_slug,),
        ).fetchone()
        return SaveMeta(**dict(row)) if row else None

    # ── saves ─────────────────────────────────────────────────────────────────

    def push_save(self, game_slug: str, device_id: str, data: bytes) -> SaveMeta:
        return self._push_blob("saves", game_slug, device_id, data)

    def pull_save(self, game_slug: str) -> tuple[Optional[bytes], Optional[SaveMeta]]:
        return self._pull_blob("saves", game_slug)

    def get_save_meta(self, game_slug: str) -> Optional[SaveMeta]:
        return self._get_blob_meta("saves", game_slug)

    # ── states ─────────────────────────────────────────────────────────────────

    def push_state(self, game_slug: str, device_id: str, data: bytes) -> SaveMeta:
        return self._push_blob("states", game_slug, device_id, data)

    def pull_state(self, game_slug: str) -> tuple[Optional[bytes], Optional[SaveMeta]]:
        return self._pull_blob("states", game_slug)

    def get_state_meta(self, game_slug: str) -> Optional[SaveMeta]:
        return self._get_blob_meta("states", game_slug)
