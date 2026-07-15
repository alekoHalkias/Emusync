"""PS2/PCSX2 shared-memcard and shared-state adapter for `emusync run` (split
out of cli/run.py, issue #368)."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click

from cli.detect import _dolphin_card_format
from cli.run_conflicts import _notify
from cli.run_reconcile import _mtime

logger = logging.getLogger("emusync.run")

# Consoles whose "save" is a single card/folder shared across every game on the
# console, so it's reconciled per-console rather than per-game: PS2 memory card
# (#295), Dreamcast VMU, Dolphin GC cards, PPSSPP SAVEDATA (#402), Azahar's 3DS
# SD-card title tree (#418). Keep in sync with scan.ts's SHARED_MEMCARD_CONSOLES
# and helpers.ts's _SHARED_SAVE_LAYOUT.
_SHARED_MEMCARD_CONSOLES = {"PS2", "DC", "GC", "PSP", "3DS"}

# Consoles that keep save states in one SHARED folder, named per game serial
# (PCSX2 sstates/<SERIAL> (<CRC>).<slot>.p2s) — synced filtered by serial (#294).
_SHARED_STATE_CONSOLES = {"PS2"}


def _ps2_state_serial_prefix(state_folder: str, since: float) -> Optional[str]:
    """The PCSX2 state-serial prefix for the .p2s written this session, e.g.
    ``"SLUS-20062 ("`` — files starting with it are exactly this game's states in
    the shared sstates folder, so we can pack just them (issue #294). None when no
    state was written this session (nothing changed to push)."""
    folder = Path(state_folder)
    if not folder.is_dir():
        return None
    written = [f for f in folder.glob("*.p2s") if _mtime(f) >= since]
    if not written:
        return None
    newest = max(written, key=_mtime)
    serial = newest.name.split(" (", 1)[0]
    return f"{serial} ("


def _warn_card_format_mismatch(cfg, local_format: str, remote_format: str) -> None:
    """Surface a GC memory-card format mismatch: stderr + notification + a
    current-state file (overwritten, not appended — this describes an ongoing
    misconfiguration, not a one-off event like save_conflicts.json) (#428)."""
    msg = (
        f"GameCube memory card sync skipped: this device's Dolphin is configured for "
        f"'{local_format}' but the last-synced card is '{remote_format}'. Saves won't "
        f"sync until every device's Dolphin uses the same Config -> GameCube -> Slot A/B "
        f"setting (or you convert the card via Dolphin's own 'Convert File' feature)."
    )
    click.echo(f"⚠ {msg}", err=True)
    _notify("EmuSync — GC memory card format mismatch", msg)
    try:
        path = Path(cfg.data_dir) / "card_format_mismatch.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "console_key": "GC",
            "local_format": local_format,
            "remote_format": remote_format,
            "detected_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2))
    except Exception:
        logger.warning("failed to write card_format_mismatch.json", exc_info=True)


class _MemcardClient:
    """Adapts the per-game save API (used by `_reconcile_save` and the post-game
    push) onto the console-scoped shared memory-card endpoints, so the shared card
    reconciles with the exact same newest-wins / `.bak` logic. The `slug` args are
    the console key (e.g. ``"PS2"``) and are forwarded as the console_key (#295)."""

    def __init__(self, client, console_key: str, cfg=None) -> None:
        self._client = client
        self._key = console_key
        self._cfg = cfg
        self._last_meta: Optional[dict] = None

    def get_save_meta(self, _slug: str):
        self._last_meta = self._client.get_console_memcard_meta(self._key)
        return self._last_meta

    def push_save(self, _slug: str, path: str) -> str:
        card_format = _dolphin_card_format(path) if self._key == "GC" else ""
        return self._client.push_console_memcard(self._key, path, card_format=card_format)

    def pull_save(self, _slug: str, path: str):
        if self._key == "GC":
            remote_format = (self._last_meta or {}).get("card_format") or ""
            local_format = _dolphin_card_format(path)
            if (remote_format not in ("", "unknown") and local_format not in ("", "unknown")
                    and remote_format != local_format):
                _warn_card_format_mismatch(self._cfg, local_format, remote_format)
                return False, None
        return self._client.pull_console_memcard(self._key, path)

    def report_conflict(self, *args, **kwargs) -> None:
        # No game row backs a console artifact, so there's nothing to record in the
        # per-game Conflicts panel; the local log + notification still happen.
        return None


# PCSX2 records per-game play data in inis/playtime.dat, keyed by disc serial:
#   <SERIAL>   <total_seconds>   <last_played_unix>
# We use it to learn a PS2 game's serial (the row it freshly timestamps after a
# session) so the GUI can show a real per-game last-played despite the shared
# memory card (issue #301).
_PCSX2_PLAYTIME_FILES = (
    Path.home() / ".config/PCSX2/inis/playtime.dat",
    Path.home() / ".var/app/net.pcsx2.PCSX2/config/PCSX2/inis/playtime.dat",
)


def _read_pcsx2_playtime() -> dict[str, dict]:
    """serial → {'seconds': int, 'last_played': int} from PCSX2's playtime.dat."""
    out: dict[str, dict] = {}
    for f in _PCSX2_PLAYTIME_FILES:
        if not f.exists():
            continue
        try:
            for line in f.read_text().splitlines():
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        out[parts[0]] = {"seconds": int(parts[1]), "last_played": int(parts[2])}
                    except ValueError:
                        continue
        except Exception:
            logger.debug("could not read PCSX2 playtime file %s", f, exc_info=True)
        break
    return out


def _learn_ps2_serial(cfg, game_slug: str, since: float) -> None:
    """Map this PS2 game to the serial PCSX2 just played, so the GUI can show its
    last-played (issue #301). The freshly-played game is the playtime.dat row with
    the newest ``last_played`` at/after this session's launch. Persisted to
    ``ps2_serials.json`` (slug → serial); a no-op if PCSX2 recorded nothing."""
    played = [
        (serial, d["last_played"])
        for serial, d in _read_pcsx2_playtime().items()
        if d["last_played"] >= since
    ]
    if not played:
        return
    serial = max(played, key=lambda x: x[1])[0]
    path = Path(cfg.data_dir) / "ps2_serials.json"
    try:
        data = json.loads(path.read_text()) if path.exists() else {}
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    if data.get(game_slug) == serial:
        return
    data[game_slug] = serial
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2))
    except Exception:
        logger.warning("failed to write %s", path, exc_info=True)
