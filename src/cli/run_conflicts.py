"""Save-safety checks and auto-resolved-conflict logging/notification for
`emusync run` (split out of cli/run.py, issue #368)."""
from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click

logger = logging.getLogger("emusync.run")


def _notify(title: str, msg: str) -> None:
    """Best-effort, non-blocking desktop notification (so a Steam launch, which
    shows no terminal, still surfaces a conflict). Silently no-ops if unavailable.

    Uses normal urgency + a 3 s expire time so the toast auto-dismisses (issue
    #218) — `critical` urgency would make compositors keep it on screen forever.
    """
    try:
        subprocess.Popen(
            ["notify-send", "--app-name=EmuSync", "--urgency=normal", "-t", "3000", title, msg],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def _log_save_conflict(cfg, game_slug: str, winner: str, local_hash: Optional[str], server_meta: Optional[dict]) -> None:
    """Append a record of an auto-resolved save divergence to save_conflicts.json."""
    entry = {
        "slug": game_slug,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
        "winner": winner,  # "local" or "server"
        "local_hash": local_hash,
        "server_hash": server_meta.get("hash") if server_meta else None,
        "server_pushed_at": server_meta.get("pushed_at") if server_meta else None,
    }
    path = Path(cfg.data_dir) / "save_conflicts.json"
    try:
        existing = json.loads(path.read_text()) if path.exists() else []
        if not isinstance(existing, list):
            existing = []
    except Exception:
        logger.debug("could not read existing %s; starting fresh", path, exc_info=True)
        existing = []
    existing.append(entry)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(existing, indent=2))
    except Exception:
        logger.warning("failed to write save conflict log %s", path, exc_info=True)


# A post-game save that is empty, or has shrunk to below this fraction of the
# previous server copy, is treated as corruption (e.g. a crashed/force-killed
# emulator left a truncated file) and is NOT pushed, so it can't destroy the good
# server copy (issue #213). SRAM is fixed-size, so a legitimate save never trips
# this; the floor is deliberately generous to avoid false positives.
_SAVE_SHRINK_FLOOR = 0.5


def _save_is_safe_to_push(local_size: int, server_size: Optional[int], floor: float = _SAVE_SHRINK_FLOOR) -> bool:
    """Whether a freshly-written save is safe to push over the server's copy.

    Refuses a 0-byte save outright, and refuses one that has shrunk below *floor*
    of the previous server save (a strong truncation signal). When the server has
    no prior save, any non-empty save is allowed (it's the first one).
    """
    if local_size <= 0:
        return False
    if not server_size or server_size <= 0:
        return True
    return local_size >= server_size * floor


def _warn_unsafe_save(cfg, game_slug: str, local_size: int, server_size: Optional[int]) -> None:
    """Surface a refused (likely-truncated) save: stderr + desktop notification."""
    detail = (
        f"the save written this session is {local_size} bytes"
        + (f" (was {server_size} bytes)" if server_size else "")
        + " — it looks truncated/corrupt, so it was NOT pushed. The good server copy "
        "was kept. If this was intentional, re-save in the emulator and play again."
    )
    msg = f"Refused to sync save for '{game_slug}': {detail}"
    click.echo(f"⚠ {msg}", err=True)
    _notify("EmuSync — save not synced", msg)


def _report_conflict_to_server(client, cfg, game_slug: str, winner: str,
                               local_hash: Optional[str], server_meta: Optional[dict]) -> None:
    """Record the resolved divergence on the server so the GUI Conflicts panel can
    show it from any device (issue #243). Best-effort — local logging already
    happened, so a failure here is non-fatal."""
    try:
        server_device = (server_meta or {}).get("device_id", "")
        server_hash = (server_meta or {}).get("hash", "")
        this_device = getattr(cfg, "device_id", "")
        if winner == "local":
            winner_device, loser_device = this_device, server_device
            winner_hash, loser_hash = local_hash or "", server_hash
        else:
            winner_device, loser_device = server_device, this_device
            winner_hash, loser_hash = server_hash, local_hash or ""
        client.report_conflict(game_slug, winner_device, loser_device, winner_hash, loser_hash)
    except Exception:
        logger.warning("failed to report save conflict for '%s' to server", game_slug, exc_info=True)


def _warn_save_conflict(client, cfg, game_slug: str, winner: str, local_hash: Optional[str], server_meta: Optional[dict]) -> None:
    """Surface an auto-resolved divergence: stderr + notification + local log + server record."""
    if winner == "local":
        detail = ("this device's save is newer, so it was kept and pushed; the server's "
                  "older copy was replaced (its hash is recorded in save_conflicts.json)")
    else:
        detail = ("the server's save is newer, so it was pulled; this device's previous "
                  "save was backed up to a .bak file next to it")
    msg = (f"Save conflict for '{game_slug}': both copies changed since the last sync — {detail}.")
    click.echo(f"⚠ {msg}", err=True)
    _log_save_conflict(cfg, game_slug, winner, local_hash, server_meta)
    _report_conflict_to_server(client, cfg, game_slug, winner, local_hash, server_meta)
    _notify("EmuSync — save conflict resolved", msg)
