"""Save and state blob storage.

The bytes live on disk under ``<data_dir>/blobs/<saves|states>/<row id>``; only
metadata (hash, pushed_at, size, owning device) lives in SQLite (issue #239). This
keeps the database small even with large state archives and 20 retained
generations per game, and lets reads/writes stream instead of buffering whole
blobs in memory.

Saves and states share identical storage, so private helpers parameterised by
table name back the public save/state methods.

Each push keeps the previous generations (up to ``HISTORY_LIMIT`` per game) instead
of overwriting, so a bad sync can be rolled back (issue #7). The *current* blob is
simply the most recently inserted row (ordered by SQLite ``rowid``, which is
monotonic for inserts and so unambiguous even when two pushes share a timestamp).
"""
from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from server.store.models import SaveMeta

# How many generations to retain per game, per blob table. Older rows (and their
# on-disk files) are pruned on every push.
HISTORY_LIMIT = 20


class SaveStateMixin:
    """Operates on `self._conn` and `self._blob_dir`; mixed into Store."""

    # ── on-disk layout ─────────────────────────────────────────────────────────

    def _blob_path(self, table: str, blob_id: str) -> Path:
        return self._blob_dir / table / blob_id

    def new_upload_path(self) -> Path:
        """A fresh temp path (under the blob root, so a move into place is same-fs)
        for the API to stream an incoming blob into before it's committed."""
        up = self._blob_dir / ".uploads"
        up.mkdir(parents=True, exist_ok=True)
        return up / f"{uuid.uuid4()}.part"

    # ── shared private helpers ─────────────────────────────────────────────────

    def _newest_row(self, table: str, game_slug: str):
        return self._conn.execute(
            f"SELECT id, device_id, hash, pushed_at, size FROM {table} "
            f"WHERE game_slug = ? ORDER BY rowid DESC LIMIT 1",
            (game_slug,),
        ).fetchone()

    def _insert_blob_row(self, table: str, game_slug: str, device_id: str, h: str, size: int, now: str) -> str:
        blob_id = str(uuid.uuid4())
        self._conn.execute(
            f"INSERT INTO {table} (id, game_slug, device_id, hash, pushed_at, size) "
            f"VALUES (?, ?, ?, ?, ?, ?)",
            (blob_id, game_slug, device_id, h, now, size),
        )
        return blob_id

    def _push_blob(self, table: str, game_slug: str, device_id: str, data: bytes) -> SaveMeta:
        """Store *data* as a new generation, writing the bytes to disk."""
        h = hashlib.sha256(data).hexdigest()
        now = datetime.now(timezone.utc).isoformat()
        current = self._newest_row(table, game_slug)
        # Dedupe: identical to the current blob → don't create another generation.
        if current and current["hash"] == h:
            return SaveMeta(
                game_slug=game_slug, device_id=current["device_id"],
                hash=current["hash"], pushed_at=current["pushed_at"], size=current["size"],
            )
        blob_id = self._insert_blob_row(table, game_slug, device_id, h, len(data), now)
        # Write the file before committing so a crash never leaves a row without bytes.
        self._blob_path(table, blob_id).write_bytes(data)
        self._prune_history(table, game_slug)
        self._conn.commit()
        return SaveMeta(game_slug=game_slug, device_id=device_id, hash=h, pushed_at=now, size=len(data))

    def _push_blob_file(self, table: str, game_slug: str, device_id: str, src: Path, h: str, size: int) -> SaveMeta:
        """Store an already-staged file (streamed by the API) as a new generation.

        *src* is moved into the blob store (same filesystem — see new_upload_path),
        so nothing is buffered in memory. On a content-dedupe hit the staged file is
        discarded and the existing generation is returned unchanged.
        """
        now = datetime.now(timezone.utc).isoformat()
        current = self._newest_row(table, game_slug)
        if current and current["hash"] == h:
            Path(src).unlink(missing_ok=True)
            return SaveMeta(
                game_slug=game_slug, device_id=current["device_id"],
                hash=current["hash"], pushed_at=current["pushed_at"], size=current["size"],
            )
        blob_id = self._insert_blob_row(table, game_slug, device_id, h, size, now)
        os.replace(src, self._blob_path(table, blob_id))
        self._prune_history(table, game_slug)
        self._conn.commit()
        return SaveMeta(game_slug=game_slug, device_id=device_id, hash=h, pushed_at=now, size=size)

    def _prune_history(self, table: str, game_slug: str) -> None:
        """Delete all but the newest HISTORY_LIMIT generations (rows + files)."""
        ids = [
            r["id"] for r in self._conn.execute(
                f"SELECT id FROM {table} WHERE game_slug = ? ORDER BY rowid DESC", (game_slug,)
            ).fetchall()
        ]
        for blob_id in ids[HISTORY_LIMIT:]:
            self._blob_path(table, blob_id).unlink(missing_ok=True)
        self._conn.execute(
            f"""DELETE FROM {table}
                WHERE game_slug = ? AND rowid NOT IN (
                    SELECT rowid FROM {table} WHERE game_slug = ? ORDER BY rowid DESC LIMIT ?
                )""",
            (game_slug, game_slug, HISTORY_LIMIT),
        )

    def _meta_from_row(self, game_slug: str, row) -> SaveMeta:
        return SaveMeta(
            game_slug=game_slug, device_id=row["device_id"],
            hash=row["hash"], pushed_at=row["pushed_at"], size=row["size"],
        )

    def _pull_blob_path(self, table: str, game_slug: str) -> tuple[Optional[Path], Optional[SaveMeta]]:
        """The current blob's on-disk path + meta, or (None, None). For streaming."""
        row = self._newest_row(table, game_slug)
        if not row:
            return None, None
        path = self._blob_path(table, row["id"])
        if not path.exists():
            return None, None
        return path, self._meta_from_row(game_slug, row)

    def _pull_blob(self, table: str, game_slug: str) -> tuple[Optional[bytes], Optional[SaveMeta]]:
        path, meta = self._pull_blob_path(table, game_slug)
        if path is None:
            return None, None
        return path.read_bytes(), meta

    def _get_blob_meta(self, table: str, game_slug: str) -> Optional[SaveMeta]:
        row = self._newest_row(table, game_slug)
        return self._meta_from_row(game_slug, row) if row else None

    def _list_blob_history(self, table: str, game_slug: str) -> list[dict]:
        """Return every retained generation for a game, newest first."""
        rows = self._conn.execute(
            f"""SELECT id, device_id, hash, pushed_at, size
                FROM {table} WHERE game_slug = ? ORDER BY rowid DESC""",
            (game_slug,),
        ).fetchall()
        return [dict(r) for r in rows]

    def _restore_blob(self, table: str, game_slug: str, version_id: str) -> Optional[SaveMeta]:
        """Make a past generation current by re-pushing its bytes as a new row.

        Restoring never destroys history: the chosen version's content is pushed as
        a fresh generation (subject to the same dedupe + prune rules), so the
        timeline keeps growing forward. Returns None if the version doesn't exist
        for this game.
        """
        row = self._conn.execute(
            f"SELECT device_id FROM {table} WHERE id = ? AND game_slug = ?",
            (version_id, game_slug),
        ).fetchone()
        if not row:
            return None
        src = self._blob_path(table, version_id)
        if not src.exists():
            return None
        return self._push_blob(table, game_slug, row["device_id"], src.read_bytes())

    def delete_blobs_for_game(self, game_slug: str) -> None:
        """Unlink every on-disk blob for a game (its rows are dropped by FK cascade
        when the game is removed, but the files are not)."""
        for table in ("saves", "states"):
            for r in self._conn.execute(
                f"SELECT id FROM {table} WHERE game_slug = ?", (game_slug,)
            ).fetchall():
                self._blob_path(table, r["id"]).unlink(missing_ok=True)

    # ── saves ─────────────────────────────────────────────────────────────────

    def push_save(self, game_slug: str, device_id: str, data: bytes) -> SaveMeta:
        return self._push_blob("saves", game_slug, device_id, data)

    def push_save_file(self, game_slug: str, device_id: str, src: Path, h: str, size: int) -> SaveMeta:
        return self._push_blob_file("saves", game_slug, device_id, src, h, size)

    def pull_save(self, game_slug: str) -> tuple[Optional[bytes], Optional[SaveMeta]]:
        return self._pull_blob("saves", game_slug)

    def pull_save_path(self, game_slug: str) -> tuple[Optional[Path], Optional[SaveMeta]]:
        return self._pull_blob_path("saves", game_slug)

    def get_save_meta(self, game_slug: str) -> Optional[SaveMeta]:
        return self._get_blob_meta("saves", game_slug)

    def list_save_history(self, game_slug: str) -> list[dict]:
        return self._list_blob_history("saves", game_slug)

    def restore_save(self, game_slug: str, version_id: str) -> Optional[SaveMeta]:
        return self._restore_blob("saves", game_slug, version_id)

    # ── states ─────────────────────────────────────────────────────────────────

    def push_state(self, game_slug: str, device_id: str, data: bytes) -> SaveMeta:
        return self._push_blob("states", game_slug, device_id, data)

    def push_state_file(self, game_slug: str, device_id: str, src: Path, h: str, size: int) -> SaveMeta:
        return self._push_blob_file("states", game_slug, device_id, src, h, size)

    def pull_state(self, game_slug: str) -> tuple[Optional[bytes], Optional[SaveMeta]]:
        return self._pull_blob("states", game_slug)

    def pull_state_path(self, game_slug: str) -> tuple[Optional[Path], Optional[SaveMeta]]:
        return self._pull_blob_path("states", game_slug)

    def get_state_meta(self, game_slug: str) -> Optional[SaveMeta]:
        return self._get_blob_meta("states", game_slug)

    def list_state_history(self, game_slug: str) -> list[dict]:
        return self._list_blob_history("states", game_slug)

    def restore_state(self, game_slug: str, version_id: str) -> Optional[SaveMeta]:
        return self._restore_blob("states", game_slug, version_id)
