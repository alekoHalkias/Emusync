"""Schema v38: convert every stored blob to the manifest format once (#739).

Called from ``schema._migrate``. Order of operations per file keeps a copy of
the bytes somewhere at every moment: the new blob is written to ``<id>.v38.part``
and verified, the original is copied to ``blobs/.pre-v38/<table>/<rel>``, then the
``.part`` replaces it. The database is backed up to ``emusync.db.pre-v38`` first.
Neither backup is deleted automatically.

Folder hashes change (they are now manifest hashes, see server/blob_tree.py), so
each converted row's hash is rewritten and every baseline / conflict record that
held the old hash for the same owner is remapped with it; otherwise each device's
first reconcile would read the format change as a conflict (#460). Single-file
hashes are unchanged. Every row's ``size`` becomes content bytes.

Idempotent (format-3 files are skipped). A file that cannot be converted is
reported on stderr and left as is; startup never fails.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from pathlib import Path

from server.blob_tree import _ENVELOPE_MAGIC, _FMT_TREE, legacy_to_tree, manifest_size, verify_blob

# blob table -> (owner column, baseline table, conflict table); states have neither.
_HISTORY = {
    "saves": ("game_slug", "save_sync_baseline", "save_conflicts"),
    "states": ("game_slug", None, None),
    "console_save_history": ("console_key", "console_save_sync_baseline", "console_save_conflicts"),
}


def _backup_db(conn, dest: Path) -> None:
    if dest.exists():
        return
    try:
        conn.commit()
        target = sqlite3.connect(str(dest))
        try:
            conn.backup(target)
        finally:
            target.close()
        os.chmod(dest, 0o600)
    except (sqlite3.Error, OSError, AttributeError) as e:
        print(f"emusync: v38 could not back up the database to {dest}: {e}", file=sys.stderr)


def _convert_file(root: Path, table: str, f: Path):
    """Convert one blob file; (manifest, hash) if converted, None if skipped."""
    with open(f, "rb") as fh:
        head = fh.read(len(_ENVELOPE_MAGIC) + 1)
    if head == _ENVELOPE_MAGIC + bytes([_FMT_TREE]):
        return None
    if head[:4] != _ENVELOPE_MAGIC:
        raise ValueError("no format header (v36 should have added one)")
    data = f.read_bytes()
    new = legacy_to_tree(data[4], data[5:])
    m, h = verify_blob(new)
    part = f.with_name(f.name + ".v38.part")
    try:
        part.write_bytes(new)
        orig = root / ".pre-v38" / table / f.relative_to(root / table)
        orig.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, orig)
        os.replace(part, f)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    return m, h


def _update_rows(conn, table: str, rel: str, m: dict, h: str, remap: dict) -> None:
    size = manifest_size(m)
    if table == "switch_mods":
        title_id, _, name = rel.partition("/")
        conn.execute("UPDATE switch_mods SET size = ? WHERE title_id = ? AND mod_name = ?",
                     (size, title_id, name[:-4] if name.endswith(".tar") else name))
        return
    owner_col = _HISTORY[table][0]
    row = conn.execute(f"SELECT {owner_col}, hash FROM {table} WHERE id = ?", (rel,)).fetchone()
    if row is None:
        return
    conn.execute(f"UPDATE {table} SET hash = ?, size = ? WHERE id = ?", (h, size, rel))
    if row[1] != h:
        remap[(table, row[0], row[1])] = h


def _remap_hashes(conn, remap: dict) -> None:
    for (table, owner, old), new in remap.items():
        owner_col, baseline, conflicts = _HISTORY[table]
        if baseline:
            conn.execute(f"UPDATE {baseline} SET hash = ? WHERE {owner_col} = ? AND hash = ?", (new, owner, old))
        if conflicts:
            for col in ("winner_hash", "loser_hash"):
                conn.execute(f"UPDATE {conflicts} SET {col} = ? WHERE {owner_col} = ? AND {col} = ?",
                             (new, owner, old))


def convert_blobs_to_tree(conn, blob_dir) -> None:
    root = Path(blob_dir)
    if not root.is_dir():
        return
    _backup_db(conn, root.parent / "emusync.db.pre-v38")
    remap: dict = {}
    converted = failed = 0
    for table in (*_HISTORY, "switch_mods"):  # not the retired console_saves (#737)
        d = root / table
        if not d.is_dir():
            continue
        for f in sorted(d.rglob("*")):
            if not f.is_file() or f.name.endswith(".part"):
                continue
            rel = f.relative_to(d).as_posix()
            try:
                res = _convert_file(root, table, f)
                if res is not None:
                    _update_rows(conn, table, rel, *res, remap)
                    converted += 1
            except (OSError, ValueError, sqlite3.Error) as e:
                failed += 1
                print(f"emusync: v38 could not convert {f}: {e}", file=sys.stderr)
    try:
        _remap_hashes(conn, remap)
    except sqlite3.Error as e:
        print(f"emusync: v38 could not remap sync baselines: {e}", file=sys.stderr)
    conn.commit()
    if converted or failed:
        print(f"emusync: v38 converted {converted} blob(s) to the manifest format, {failed} failed; "
              f"originals kept in {root / '.pre-v38'}", file=sys.stderr)
