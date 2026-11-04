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
from server.sync_client import _ENVELOPE_HEADER_LEN, _ENVELOPE_MAGIC

# How many generations to retain per game, per blob table. Older rows (and their
# on-disk files) are pruned on every push.
HISTORY_LIMIT = 5

# A current blob that shrank below this fraction of the generation before it is
# treated as truncated (a crashed/SIGKILLed emulator signal). Mirrors
# ``cli.run._SAVE_SHRINK_FLOOR`` — kept as a separate server-side copy so the
# store never imports from the CLI (issue #285).
_SHRINK_FLOOR = 0.5


def _payload_sha256(data: bytes) -> str:
    """Content hash of a stored blob, excluding the #478 transfer envelope header.

    Must match api/blobs.py:_stage_upload, which records the envelope-free hash
    on push; hashing the full bytes flags every enveloped blob as damaged and
    gives restored generations hashes no client can match (#734).
    """
    if data[:len(_ENVELOPE_MAGIC)] == _ENVELOPE_MAGIC:
        data = data[_ENVELOPE_HEADER_LEN:]
    return hashlib.sha256(data).hexdigest()


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

    # Every helper below takes the owning column (`owner_col`): "game_slug" for the
    # saves/states tables, "console_key" for console_save_history (#737). The
    # argument named game_slug carries the owner value either way. Console rows
    # also carry `card_format` (#428), passed as `card_format` and None elsewhere.

    def _newest_row(self, table: str, game_slug: str, owner_col: str = "game_slug"):
        extra = ", card_format" if owner_col == "console_key" else ""
        return self._conn.execute(
            f"SELECT id, device_id, hash, pushed_at, size{extra} FROM {table} "
            f"WHERE {owner_col} = ? ORDER BY rowid DESC LIMIT 1",
            (game_slug,),
        ).fetchone()

    def _insert_blob_row(self, table: str, game_slug: str, device_id: str, h: str, size: int, now: str,
                         owner_col: str = "game_slug", card_format: Optional[str] = None,
                         blob_id: Optional[str] = None) -> str:
        blob_id = blob_id or str(uuid.uuid4())
        cols, vals = ["id", owner_col, "device_id", "hash", "pushed_at", "size"], [blob_id, game_slug, device_id, h, now, size]
        if owner_col == "console_key":
            cols.append("card_format")
            vals.append(card_format or "")
        self._conn.execute(
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", vals,
        )
        return blob_id

    def _push_blob(self, table: str, game_slug: str, device_id: str, data: bytes,
                   owner_col: str = "game_slug", card_format: Optional[str] = None) -> SaveMeta:
        """Store *data* as a new generation, writing the bytes to disk."""
        h = _payload_sha256(data)
        now = datetime.now(timezone.utc).isoformat()
        current = self._newest_row(table, game_slug, owner_col)
        # Dedupe: identical to the current blob → don't create another generation.
        if current and current["hash"] == h:
            return SaveMeta(
                game_slug=game_slug, device_id=current["device_id"],
                hash=current["hash"], pushed_at=current["pushed_at"], size=current["size"],
            )
        blob_id = self._insert_blob_row(table, game_slug, device_id, h, len(data), now, owner_col, card_format)
        # Write the file before committing so a crash never leaves a row without bytes.
        self._blob_path(table, blob_id).write_bytes(data)
        stale = self._prune_history(table, game_slug, owner_col)
        self._conn.commit()
        self._unlink_blobs(table, stale)
        return SaveMeta(game_slug=game_slug, device_id=device_id, hash=h, pushed_at=now, size=len(data))

    def _push_blob_file(self, table: str, game_slug: str, device_id: str, src: Path, h: str, size: int,
                        owner_col: str = "game_slug", card_format: Optional[str] = None) -> SaveMeta:
        """Store an already-staged file (streamed by the API) as a new generation.

        *src* is moved into the blob store (same filesystem — see new_upload_path),
        so nothing is buffered in memory. On a content-dedupe hit the staged file is
        discarded and the existing generation is returned unchanged.
        """
        now = datetime.now(timezone.utc).isoformat()
        current = self._newest_row(table, game_slug, owner_col)
        if current and current["hash"] == h:
            Path(src).unlink(missing_ok=True)
            return SaveMeta(
                game_slug=game_slug, device_id=current["device_id"],
                hash=current["hash"], pushed_at=current["pushed_at"], size=current["size"],
            )
        # Move the file in first, then the row: a failed move must not leave an
        # uncommitted row for the next commit on this connection to persist (#704).
        blob_id = str(uuid.uuid4())
        dest = self._blob_path(table, blob_id)
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(src, dest)
            self._insert_blob_row(table, game_slug, device_id, h, size, now, owner_col, card_format, blob_id)
            stale = self._prune_history(table, game_slug, owner_col)
            self._conn.commit()
        except BaseException:
            self._conn.rollback()
            dest.unlink(missing_ok=True)
            raise
        self._unlink_blobs(table, stale)
        return SaveMeta(game_slug=game_slug, device_id=device_id, hash=h, pushed_at=now, size=size)

    def _unlink_blobs(self, table: str, ids: list[str]) -> None:
        for blob_id in ids:
            self._blob_path(table, blob_id).unlink(missing_ok=True)

    def _prune_history(self, table: str, game_slug: str, owner_col: str = "game_slug") -> list[str]:
        """Delete rows beyond the newest HISTORY_LIMIT generations; return their ids.

        Files are unlinked by the caller *after* commit (#704)."""
        ids = [
            r["id"] for r in self._conn.execute(
                f"SELECT id FROM {table} WHERE {owner_col} = ? ORDER BY rowid DESC", (game_slug,)
            ).fetchall()
        ]
        stale = ids[HISTORY_LIMIT:]
        self._conn.execute(
            f"""DELETE FROM {table}
                WHERE {owner_col} = ? AND rowid NOT IN (
                    SELECT rowid FROM {table} WHERE {owner_col} = ? ORDER BY rowid DESC LIMIT ?
                )""",
            (game_slug, game_slug, HISTORY_LIMIT),
        )
        return stale

    def _meta_from_row(self, game_slug: str, row) -> SaveMeta:
        return SaveMeta(
            game_slug=game_slug, device_id=row["device_id"],
            hash=row["hash"], pushed_at=row["pushed_at"], size=row["size"],
        )

    def _pull_blob_path(self, table: str, game_slug: str, owner_col: str = "game_slug") -> tuple[Optional[Path], Optional[SaveMeta]]:
        """The current blob's on-disk path + meta, or (None, None). For streaming."""
        row = self._newest_row(table, game_slug, owner_col)
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

    def _list_blob_history(self, table: str, game_slug: str, owner_col: str = "game_slug") -> list[dict]:
        """Return every retained generation for a game, newest first."""
        extra = ", card_format" if owner_col == "console_key" else ""
        rows = self._conn.execute(
            f"""SELECT id, device_id, hash, pushed_at, size{extra}
                FROM {table} WHERE {owner_col} = ? ORDER BY rowid DESC""",
            (game_slug,),
        ).fetchall()
        return [dict(r) for r in rows]

    def _restore_blob(self, table: str, game_slug: str, version_id: str, owner_col: str = "game_slug") -> Optional[SaveMeta]:
        """Make a past generation current by re-pushing its bytes as a new row.

        Restoring never destroys history: the chosen version's content is pushed as
        a fresh generation (subject to the same dedupe + prune rules), so the
        timeline keeps growing forward. Returns None if the version doesn't exist
        for this game.
        """
        extra = ", card_format" if owner_col == "console_key" else ""
        row = self._conn.execute(
            f"SELECT device_id{extra} FROM {table} WHERE id = ? AND {owner_col} = ?",
            (version_id, game_slug),
        ).fetchone()
        if not row:
            return None
        src = self._blob_path(table, version_id)
        if not src.exists():
            return None
        return self._push_blob(table, game_slug, row["device_id"], src.read_bytes(), owner_col,
                               row["card_format"] if extra else None)

    # ── integrity ───────────────────────────────────────────────────────────────

    def _classify_blob(self, table: str, game_slug: str, owner_col: str = "game_slug") -> dict:
        """Classify the *current* generation of a blob as ok / damaged / missing.

        "damaged" = 0-byte OR shrank below ``_SHRINK_FLOOR`` of the prior
        generation OR the on-disk bytes no longer match the recorded hash OR the
        backing file is gone (issue #285). The verdict is computed from data that
        already exists (row metadata + the file), so no schema column is needed.

        ``last_good_version_id`` is the newest generation whose recorded size > 0
        and whose file still hashes to its recorded hash — the target for a
        one-click "restore last good" when the current blob is damaged.
        """
        row = self._newest_row(table, game_slug, owner_col)
        if row is None:
            return {
                "status": "missing", "reasons": [], "size": None, "hash": None,
                "pushed_at": None, "prior_size": None, "last_good_version_id": None,
            }

        reasons: list[str] = []
        path = self._blob_path(table, row["id"])
        actual: Optional[int] = None
        # Compare against the generation immediately before the current one.
        prior = self._conn.execute(
            f"SELECT size FROM {table} WHERE {owner_col} = ? "
            f"ORDER BY rowid DESC LIMIT 1 OFFSET 1",
            (game_slug,),
        ).fetchone()
        if not path.exists():
            reasons.append("file_missing")
        else:
            actual = path.stat().st_size
            if actual == 0:
                reasons.append("zero_byte")
            if prior is not None and prior["size"] and actual < prior["size"] * _SHRINK_FLOOR:
                reasons.append("shrank")
            if _payload_sha256(path.read_bytes()) != row["hash"]:
                reasons.append("hash_mismatch")

        return {
            "status": "damaged" if reasons else "ok",
            "reasons": reasons,
            "size": actual,
            "hash": row["hash"],
            "pushed_at": row["pushed_at"],
            "prior_size": prior["size"] if prior else None,
            "last_good_version_id": self._last_good_version(table, game_slug, owner_col),
        }

    def _last_good_version(self, table: str, game_slug: str, owner_col: str = "game_slug") -> Optional[str]:
        """The newest generation with a non-empty file that still matches its hash."""
        for r in self._conn.execute(
            f"SELECT id, hash, size FROM {table} WHERE {owner_col} = ? ORDER BY rowid DESC",
            (game_slug,),
        ).fetchall():
            if not r["size"]:
                continue
            p = self._blob_path(table, r["id"])
            if not p.exists():
                continue
            if _payload_sha256(p.read_bytes()) == r["hash"]:
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

    # ── per-device save-sync baseline (issue #460) ───────────────────────────────
    # Not touched by state sync — conflict warnings only ever fire for saves.

    def set_save_sync_baseline(self, game_slug: str, device_id: str, h: str, synced_at: str) -> None:
        """Record *h* as the save hash *device_id* is now known to agree with the
        server on for *game_slug* — called by the push/pull API handlers after
        every successful transfer, so it covers `emusync run`, GUI manual
        push/pull, and any future caller uniformly."""
        self._set_baseline("save_sync_baseline", "game_slug", game_slug, device_id, h, synced_at)

    def get_save_sync_baseline(self, game_slug: str, device_id: str) -> Optional[dict]:
        return self._get_baseline("save_sync_baseline", "game_slug", game_slug, device_id)

    # One implementation for both baseline tables (game_slug / console_key, #737).

    def _set_baseline(self, table: str, owner_col: str, owner: str, device_id: str, h: str, synced_at: str) -> None:
        self._conn.execute(
            f"INSERT OR REPLACE INTO {table} ({owner_col}, device_id, hash, synced_at) VALUES (?, ?, ?, ?)",
            (owner, device_id, h, synced_at),
        )
        self._conn.commit()

    def _get_baseline(self, table: str, owner_col: str, owner: str, device_id: str) -> Optional[dict]:
        row = self._conn.execute(
            f"SELECT hash, synced_at FROM {table} WHERE {owner_col} = ? AND device_id = ?",
            (owner, device_id),
        ).fetchone()
        return dict(row) if row else None

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
    # PS2/DC/GC/PSP/3DS use one memory card shared across every game on the
    # console, keyed by console_key. Since #737 it runs on the same blob core as
    # saves/states (owner_col="console_key", table console_save_history): the
    # current card is the newest history row, HISTORY_LIMIT generations are kept,
    # and the pre-#737 console_saves table is no longer written (v35 backfills any
    # card that only lived there). Folder cards arrive already tarred by the client
    # (envelope), so the server stores the bytes as-is.

    _CARD_TABLE = "console_save_history"

    def push_console_save_file(self, console_key: str, device_id: str, src: Path, h: str, size: int,
                                card_format: str = "") -> dict:
        """Store a console's shared memory card as a new generation (deduped).

        `card_format` is the pushing device's configured memory-card storage
        format (e.g. Dolphin's "MemoryCard"/"GCIFolder" — issue #428), recorded
        so a pulling device can detect a mismatch before merging incompatible
        card layouts together. Empty for consoles without multiple formats.
        """
        m = self._push_blob_file(self._CARD_TABLE, console_key, device_id, src, h, size,
                                 "console_key", card_format)
        return self._card_meta(console_key, m)

    def _card_meta(self, console_key: str, m: SaveMeta) -> dict:
        """SaveMeta -> the dict shape console callers use. card_format comes from
        the row, since a dedupe hit returns the existing generation's metadata."""
        row = self._newest_row(self._CARD_TABLE, console_key, "console_key")
        return {"device_id": m.device_id, "hash": m.hash, "pushed_at": m.pushed_at, "size": m.size,
                "card_format": (row["card_format"] if row else "") or ""}

    def pull_console_save_path(self, console_key: str) -> tuple[Optional[Path], Optional[dict]]:
        """The console's shared card as (path, meta), or (None, None).

        Served from the newest history row: generation files are written once and
        never replaced, so a push landing mid-download can't swap the bytes under
        a streaming response (#734)."""
        path, m = self._pull_blob_path(self._CARD_TABLE, console_key, "console_key")
        if path is None:
            return None, None
        return path, self._card_meta(console_key, m)

    def get_console_save_meta(self, console_key: str) -> Optional[dict]:
        row = self._newest_row(self._CARD_TABLE, console_key, "console_key")
        if row is None:
            return None
        return {"device_id": row["device_id"], "hash": row["hash"], "pushed_at": row["pushed_at"],
                "size": row["size"], "card_format": row["card_format"] or ""}

    def list_console_save_history(self, console_key: str) -> list[dict]:
        """Every retained generation of a console's shared card, newest first (#480)."""
        return self._list_blob_history(self._CARD_TABLE, console_key, "console_key")

    def restore_console_save(self, console_key: str, version_id: str) -> Optional[dict]:
        """Make a past generation current by re-pushing its bytes (same dedupe /
        prune rules as a normal push; history is never destroyed). The restored
        generation keeps its card_format. None if the version doesn't exist."""
        m = self._restore_blob(self._CARD_TABLE, console_key, version_id, "console_key")
        return self._card_meta(console_key, m) if m else None

    # ── console-scoped save-sync baseline (issue #481) ───────────────────────────
    # Console-key equivalent of save_sync_baseline (#460) — see that section for
    # the full rationale. Extends the same conflict-suppression to shared-memcard
    # consoles (PS2/DC/GC/PSP/3DS), which _MemcardClient.get_save_sync_baseline
    # previously always reported as having no baseline.

    def set_console_save_sync_baseline(self, console_key: str, device_id: str, h: str, synced_at: str) -> None:
        """Record *h* as the shared-card hash *device_id* is now known to agree
        with the server on for *console_key* — called by the console memcard
        push/pull API handlers after every successful transfer."""
        self._set_baseline("console_save_sync_baseline", "console_key", console_key, device_id, h, synced_at)

    def get_console_save_sync_baseline(self, console_key: str, device_id: str) -> Optional[dict]:
        return self._get_baseline("console_save_sync_baseline", "console_key", console_key, device_id)
