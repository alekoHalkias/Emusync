"""Per-game metadata cache and manual overrides (`game_metadata`, issue #578)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

_FIELDS = ("synopsis", "release_date", "cover_url")


class MetadataMixin:
    """Operates on `self._conn`; mixed into Store."""

    def get_metadata(self, slug: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT slug, synopsis, release_date, cover_url, source, fetched_at"
            " FROM game_metadata WHERE slug = ?",
            (slug,),
        ).fetchone()
        return dict(row) if row else None

    def set_metadata(self, slug: str, fields: dict, source: str) -> bool:
        """Upsert metadata. A `manual` row is never replaced by another source.
        Returns False when the write was refused."""
        cur = self.get_metadata(slug)
        if cur and cur["source"] == "manual" and source != "manual":
            return False
        vals = [str(fields.get(k) or "") for k in _FIELDS]
        self._conn.execute(
            "INSERT OR REPLACE INTO game_metadata"
            " (slug, synopsis, release_date, cover_url, source, fetched_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (slug, *vals, source, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()
        return True

    def delete_metadata(self, slug: str) -> None:
        self._conn.execute("DELETE FROM game_metadata WHERE slug = ?", (slug,))
        self._conn.commit()
