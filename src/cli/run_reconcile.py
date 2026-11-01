"""Save/state reconciliation policy and post-launch written-path detection for
`emusync run` (split out of cli/run.py, issue #368)."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click

from cli.common import _mtime, _newest_matching, _parse_iso_utc, _find_touched_path
from cli.run_conflicts import _warn_save_conflict
from server.sync_client import _memcard_payload_bytes


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
    if not save_path:
        # No local save path is known yet (e.g. Switch before its first launch —
        # the real NAND save folder is only learned after this session,
        # cli/run_switch.py/#441). Nothing to reconcile against: Path("") would
        # otherwise resolve to the cwd, which must never be treated as a save
        # file. The caller's post-launch adoption step picks up and pushes the
        # freshly written save instead.
        # A request failure propagates: it is not "no save on the server" (#717).
        meta = client.get_save_meta(game_slug)
        return meta.get("hash") if meta else None
    p = Path(save_path)
    meta = client.get_save_meta(game_slug)  # raises on failure; None only means 204 (#717)

    local_hash: Optional[str] = None
    local_mtime: Optional[datetime] = None
    if p.exists():
        local_hash = hashlib.sha256(_memcard_payload_bytes(p)).hexdigest()
        # rglob, not iterdir: folder cards nest content (PCSX2 GAME1/GAME1,
        # PPSSPP SAVEDATA/<GAME>/, Dolphin GC/) whose changes must count (#402).
        mtime_src = max((f.stat().st_mtime for f in p.rglob("*") if f.is_file()), default=p.stat().st_mtime) if p.is_dir() else p.stat().st_mtime
        local_mtime = datetime.fromtimestamp(mtime_src, tz=timezone.utc)

    # A true divergence = BOTH sides moved away from this device's own last
    # known sync point since they last agreed — not just "local's stored hash
    # differs from whatever the server has right now", which is also true for
    # a routine catch-up pull (this device hasn't touched its copy since it
    # last synced, but some *other* device pushed in the meantime) and used to
    # get flagged as a conflict every time (issue #460). No baseline (this
    # device has never completed a save sync for this game before) falls back
    # to the old, more conservative behavior — mathematically identical to it,
    # since a None baseline can't equal either hash.
    try:
        baseline = client.get_save_sync_baseline(game_slug)
    except Exception:
        baseline = None
    baseline_hash = baseline.get("hash") if baseline else None
    server_hash_now = meta.get("hash") if meta else None
    local_changed = local_hash is not None and local_hash != baseline_hash
    server_changed = server_hash_now is not None and server_hash_now != baseline_hash
    diverged = local_changed and server_changed and local_hash != server_hash_now

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


def _saves_root(save_path: str) -> Path:
    """Directory tree to search for the real save. Saves use the content-dir
    layout savesRoot/<content>/<content>.<ext>, so the root is two levels up;
    fall back to one level for flat layouts."""
    parent = Path(save_path).parent
    grand = parent.parent
    return grand if grand != parent else parent


def _resolve_written_save(configured: str, since: float) -> Optional[str]:
    """The save file RetroArch actually wrote this session, or None if none was.

    Conservative: if our configured save was written this session, keep it. Only
    when it was *not* (RetroArch used a different content name) do we adopt the
    newest save written elsewhere under the saves root — so a working config is
    never disturbed. Also catches a same-folder extension change for free.
    """
    if not configured:
        return None
    found = _find_touched_path(
        configured, since,
        match=lambda f: f.suffix.lstrip(".").lower() in _SAVE_EXTS and ".bak" not in f.suffixes,
        search_root=_saves_root(configured)
    )
    return found


def _resolve_written_state(configured: str, since: float) -> Optional[str]:
    """The state FOLDER RetroArch actually wrote this session, or None.

    States are synced as a whole folder, so this returns a directory. Same
    conservative policy as _resolve_written_save: keep the configured folder if it
    was written, else adopt the folder containing the newest state file.
    """
    if not configured:
        return None
    folder = Path(configured)
    found = _find_touched_path(
        configured, since,
        match=lambda f: bool(_STATE_RE.search(f.name)),
        search_root=folder.parent,
        is_dir=True
    )
    return found
