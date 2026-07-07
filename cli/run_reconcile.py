"""Save/state reconciliation policy and post-launch written-path detection for
`emusync run` (split out of cli/run.py, issue #368)."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click

from cli.common import _parse_iso_utc
from cli.run_conflicts import _warn_save_conflict
from server.sync_client import memcard_bytes


def _decide_save_action(
    local_hash: Optional[str],
    local_mtime: Optional[datetime],
    server_meta: Optional[dict],
) -> str:
    """Pre-launch save reconciliation policy — returns 'push' | 'pull' | 'noop'.

    `local_hash` is None when there is no local save; `server_meta` is the
    `get_save_meta` dict ({hash, pushed_at}) or None. On a true divergence
    (both sides changed) the newer timestamp wins — the loser is preserved as a
    `.bak` by pull_save's caller — so a newer local save is never clobbered by an
    older server one (issue #5).
    """
    if local_hash is None:
        return "pull" if server_meta else "noop"
    if not server_meta:
        return "push"  # server has no save — local is authoritative
    if local_hash == server_meta.get("hash"):
        return "noop"  # identical content
    server_time = _parse_iso_utc(server_meta.get("pushed_at"))
    if server_time is None or (local_mtime is not None and local_mtime > server_time):
        return "push"
    return "pull"


def _reconcile_save(client, cfg, game_slug: str, save_path: str) -> Optional[str]:
    """Reconcile the local save with the server's before launch.

    Returns the hash now authoritative on the server, for the post-game
    push-if-changed comparison. When both copies diverged (a true conflict) the
    auto-resolution is surfaced loudly via _warn_save_conflict.
    """
    p = Path(save_path)
    try:
        meta = client.get_save_meta(game_slug)
    except Exception:
        meta = None

    local_hash: Optional[str] = None
    local_mtime: Optional[datetime] = None
    if p.exists():
        local_hash = hashlib.sha256(memcard_bytes(p)).hexdigest()
        mtime_src = max((f.stat().st_mtime for f in p.iterdir() if f.is_file()), default=p.stat().st_mtime) if p.is_dir() else p.stat().st_mtime
        local_mtime = datetime.fromtimestamp(mtime_src, tz=timezone.utc)

    # A true divergence = both sides have a save and they differ.
    diverged = local_hash is not None and meta is not None and local_hash != meta.get("hash")

    action = _decide_save_action(local_hash, local_mtime, meta)
    if action == "push":
        client.push_save(game_slug, save_path)
        if diverged:
            _warn_save_conflict(client, cfg, game_slug, "local", local_hash, meta)
        else:
            click.echo(f"Local save is newer — pushed {game_slug} to server.")
        return local_hash
    if action == "pull":
        pulled, server_hash = client.pull_save(game_slug, save_path)
        if diverged:
            _warn_save_conflict(client, cfg, game_slug, "server", local_hash, meta)
        elif pulled:
            click.echo(f"Pulled save for {game_slug}.")
        return server_hash
    return meta.get("hash") if meta else local_hash


# RetroArch names save/state files after the *content name*, which differs by
# launch method: the ROM filename when loaded by path, or the database/playlist
# label when loaded from a scanned playlist (e.g. "Pokémon Pinball_ Ruby &
# Sapphire [2003]"). So the real save/state may sit in a different folder AND/OR
# under a different extension than we configured. After the emulator exits we
# detect where it actually wrote *this session* and adopt that path (issue #210).
_SAVE_EXTS = {"srm", "sav", "save", "fla", "eep", "mcr", "rtc", "dsv", "ss0"}
_STATE_RE = re.compile(r"\.state(\d+|\.auto)?$", re.IGNORECASE)


def _mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def _saves_root(save_path: str) -> Path:
    """Directory tree to search for the real save. Saves use the content-dir
    layout savesRoot/<content>/<content>.<ext>, so the root is two levels up;
    fall back to one level for flat layouts."""
    parent = Path(save_path).parent
    grand = parent.parent
    return grand if grand != parent else parent


def _newest_matching(root: Path, since: float, match) -> Optional[Path]:
    """Newest file under *root* (recursively) modified at/after *since* for which
    match(file) is truthy, or None."""
    if not root.exists():
        return None
    best: Optional[Path] = None
    best_m = since
    for f in root.rglob("*"):
        try:
            if not f.is_file() or not match(f):
                continue
            m = _mtime(f)
        except OSError:
            continue
        if m >= since and (best is None or m > best_m):
            best, best_m = f, m
    return best


def _resolve_written_save(configured: str, since: float) -> Optional[str]:
    """The save file RetroArch actually wrote this session, or None if none was.

    Conservative: if our configured save was written this session, keep it. Only
    when it was *not* (RetroArch used a different content name) do we adopt the
    newest save written elsewhere under the saves root — so a working config is
    never disturbed. Also catches a same-folder extension change for free.
    """
    if not configured:
        return None
    p = Path(configured)
    if p.exists() and _mtime(p) >= since:
        return configured
    found = _newest_matching(
        _saves_root(configured), since,
        lambda f: f.suffix.lstrip(".").lower() in _SAVE_EXTS and ".bak" not in f.suffixes,
    )
    return str(found) if found else None


def _resolve_written_state(configured: str, since: float) -> Optional[str]:
    """The state FOLDER RetroArch actually wrote this session, or None.

    States are synced as a whole folder, so this returns a directory. Same
    conservative policy as _resolve_written_save: keep the configured folder if it
    was written, else adopt the folder containing the newest state file.
    """
    if not configured:
        return None
    folder = Path(configured)
    if folder.is_dir() and any(
        _mtime(f) >= since for f in folder.rglob("*") if f.is_file()
    ):
        return configured
    found = _newest_matching(folder.parent, since, lambda f: bool(_STATE_RE.search(f.name)))
    return str(found.parent) if found else None
