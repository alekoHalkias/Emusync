"""Communal Switch mod pool (issue #444).

Eden's ``load/<title-id-hex>/<mod-name>/`` folder holds one subfolder per mod
installed for a title. Unlike saves, this pool is purely additive and has no
generation history: a mod's bytes rarely change once packaged, and if a device
removes its own local copy that must never delete it for everyone else. Each
``(title_id, mod_name)`` is stored once, on disk under
``<data_dir>/blobs/switch_mods/<title_id>/<mod_name>.tar`` — mirrors the
console_saves single-overwrite blob shape in blobs.py, except a mod that
already exists in the pool is left untouched rather than overwritten (two
devices pushing the same mod is a routine no-op, not a conflict).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class SwitchModMixin:
    """Operates on `self._conn` and `self._blob_dir`; mixed into Store."""

    def _mod_blob_path(self, title_id: str, mod_name: str) -> Path:
        return self._blob_dir / "switch_mods" / title_id / f"{mod_name}.tar"

    def add_switch_mod(self, title_id: str, mod_name: str, device_id: str, src: Path, size: int) -> bool:
        """Store *src* (an already-staged tar file) as the pool's copy of this mod.

        Returns False without touching the pool if this (title_id, mod_name)
        already exists — *src* is discarded either way, so the caller never
        needs to clean it up itself.
        """
        existing = self._conn.execute(
            "SELECT 1 FROM switch_mods WHERE title_id = ? AND mod_name = ?", (title_id, mod_name)
        ).fetchone()
        if existing:
            Path(src).unlink(missing_ok=True)
            return False
        dest = self._mod_blob_path(title_id, mod_name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(src, dest)
        self._conn.execute(
            "INSERT INTO switch_mods (title_id, mod_name, size, pushed_by, pushed_at) VALUES (?, ?, ?, ?, ?)",
            (title_id, mod_name, size, device_id, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()
        return True

    def list_switch_mods(self, title_id: str) -> list[dict]:
        rows = self._conn.execute(
            """SELECT title_id, mod_name, size, pushed_by, pushed_at FROM switch_mods
               WHERE title_id = ? ORDER BY mod_name""",
            (title_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_switch_mod_path(self, title_id: str, mod_name: str) -> Optional[Path]:
        row = self._conn.execute(
            "SELECT 1 FROM switch_mods WHERE title_id = ? AND mod_name = ?", (title_id, mod_name)
        ).fetchone()
        if not row:
            return None
        path = self._mod_blob_path(title_id, mod_name)
        return path if path.exists() else None
