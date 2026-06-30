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

# A current blob that shrank below this fraction of the generation before it is
# treated as truncated (a crashed/SIGKILLed emulator signal). Mirrors
# ``cli.run._SAVE_SHRINK_FLOOR`` — kept as a separate server-side copy so the
# store never imports from the CLI (issue #285).
_SHRINK_FLOOR = 0.5


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

    # ── integrity ───────────────────────────────────────────────────────────────

    def _classify_blob(self, table: str, game_slug: str) -> dict:
        """Classify the *current* generation of a blob as ok / damaged / missing.

        "damaged" = 0-byte OR shrank below ``_SHRINK_FLOOR`` of the prior
        generation OR the on-disk bytes no longer match the recorded hash OR the
        backing file is gone (issue #285). The verdict is computed from data that
        already exists (row metadata + the file), so no schema column is needed.

        ``last_good_version_id`` is the newest generation whose recorded size > 0
        and whose file still hashes to its recorded hash — the target for a
        one-click "restore last good" when the current blob is damaged.
        """
        row = self._newest_row(table, game_slug)
        if row is None:
            return {
                "status": "missing", "reasons": [], "size": None, "hash": None,
                "pushed_at": None, "prior_size": None, "last_good_version_id": None,
            }

        reasons: list[str] = []
        path = self._blob_path(table, row["id"])
        actual: Optional[int] = None
        if not path.exists():
            reasons.append("file_missing")
        else:
            actual = path.stat().st_size
            if actual == 0:
                reasons.append("zero_byte")
            # Compare against the generation immediately before the current one.
            prior = self._conn.execute(
                f"SELECT size FROM {table} WHERE game_slug = ? "
                f"ORDER BY rowid DESC LIMIT 1 OFFSET 1",
                (game_slug,),
            ).fetchone()
            if prior is not None and prior["size"] and actual < prior["size"] * _SHRINK_FLOOR:
                reasons.append("shrank")
            if hashlib.sha256(path.read_bytes()).hexdigest() != row["hash"]:
                reasons.append("hash_mismatch")

        prior_row = self._conn.execute(
            f"SELECT size FROM {table} WHERE game_slug = ? "
            f"ORDER BY rowid DESC LIMIT 1 OFFSET 1",
            (game_slug,),
        ).fetchone()

        return {
            "status": "damaged" if reasons else "ok",
            "reasons": reasons,
            "size": actual,
            "hash": row["hash"],
            "pushed_at": row["pushed_at"],
            "prior_size": prior_row["size"] if prior_row else None,
            "last_good_version_id": self._last_good_version(table, game_slug),
        }

    def _last_good_version(self, table: str, game_slug: str) -> Optional[str]:
        """The newest generation with a non-empty file that still matches its hash."""
        for r in self._conn.execute(
            f"SELECT id, hash, size FROM {table} WHERE game_slug = ? ORDER BY rowid DESC",
            (game_slug,),
        ).fetchall():
            if not r["size"]:
                continue
            p = self._blob_path(table, r["id"])
            if not p.exists():
                continue
            if hashlib.sha256(p.read_bytes()).hexdigest() == r["hash"]:
                return r["id"]
        return None

    def integrity_for_game(self, game_slug: str) -> dict:
        """Integrity verdicts for a game's current save and state blobs."""
        return {
            "save": self._classify_blob("saves", game_slug),
            "state": self._classify_blob("states", game_slug),
        }

    def sweep_integrity(self) -> dict[str, dict]:
        """Classify every game that has at least one save or state generation."""
        slugs = {
            r["game_slug"] for r in self._conn.execute(
                "SELECT game_slug FROM saves UNION SELECT game_slug FROM states"
            ).fetchall()
        }
        return {slug: self.integrity_for_game(slug) for slug in slugs}

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

    # ── console-scoped shared save (one memory card per console, issue #295) ─────
    #
    # PS2 uses a single memory card shared across every game on the console, which
    # doesn't fit the per-game save model. It's stored once per console_key, single
    # generation (overwrite), bytes on disk under blobs/console_saves/<key>.

    def push_console_save_file(self, console_key: str, device_id: str, src: Path, h: str, size: int) -> dict:
        """Store a console's shared memory card, overwriting the previous copy."""
        now = datetime.now(timezone.utc).isoformat()
        row = self._conn.execute(
            "SELECT device_id, hash, pushed_at, size FROM console_saves WHERE console_key = ?",
            (console_key,),
        ).fetchone()
        if row and row["hash"] == h:
            Path(src).unlink(missing_ok=True)  # identical content — keep what's there
            return dict(row)
        dest = self._blob_path("console_saves", console_key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(src, dest)
        self._conn.execute(
            "INSERT INTO console_saves (console_key, device_id, hash, pushed_at, size) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(console_key) DO UPDATE SET "
            "device_id=excluded.device_id, hash=excluded.hash, pushed_at=excluded.pushed_at, size=excluded.size",
            (console_key, device_id, h, now, size),
        )
        self._conn.commit()
        return {"device_id": device_id, "hash": h, "pushed_at": now, "size": size}

    def pull_console_save_path(self, console_key: str) -> tuple[Optional[Path], Optional[dict]]:
        """The console's shared-card on-disk path + meta, or (None, None)."""
        meta = self.get_console_save_meta(console_key)
        if meta is None:
            return None, None
        path = self._blob_path("console_saves", console_key)
        if not path.exists():
            return None, None
        return path, meta

    def get_console_save_meta(self, console_key: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT device_id, hash, pushed_at, size FROM console_saves WHERE console_key = ?",
            (console_key,),
        ).fetchone()
        return dict(row) if row else None
