"""Wii NAND per-title save adapter for `emusync run` (issue #431).

Dolphin emulates the Wii's NAND as a real directory tree, not a packed binary
image: ``Wii/title/<type-hex>/<id-hex>/data/`` holds one folder per installed
title. Disc-based games are always type ``00010000``; ``<id-hex>`` is the
game's 4-character ASCII ID hex-encoded, so it's identical across every device
that owns the same disc (unlike PS2/PCSX2, there is no per-install playtime
log to read it from directly). ``content/`` holds install-time ticket data and
must never be touched; ``00000001/*`` holds system titles (System Menu, IOS)
and must never be touched either.

Since the game <-> title-ID folder mapping isn't knowable before the game has
been played at least once, it's learned the same way #210's RetroArch
content-name mismatch is: after a session, find what was actually written and
adopt that path (see cli/run_reconcile.py's _resolve_written_save for the
RetroArch equivalent this mirrors).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import click

from cli.run_reconcile import _mtime

# Native + flatpak Wii NAND roots (mirrors _DOLPHIN's native/flatpak GC paths
# in cli/consoles_data.py, one level up from the GC folder).
_WII_NAND_ROOTS = (
    Path.home() / ".local/share/dolphin-emu/Wii",
    Path.home() / ".var/app/org.DolphinEmu.dolphin-emu/data/dolphin-emu/Wii",
)

# Disc-based games only — the only title type this app ever imports ROMs for.
_DISC_TITLE_TYPE = "00010000"


def _wii_title_data_dirs() -> list[Path]:
    """Every disc-game title's ``data/`` folder across both NAND roots."""
    dirs: list[Path] = []
    for root in _WII_NAND_ROOTS:
        type_dir = root / "title" / _DISC_TITLE_TYPE
        if not type_dir.is_dir():
            continue
        for title_dir in type_dir.iterdir():
            data_dir = title_dir / "data"
            if data_dir.is_dir():
                dirs.append(data_dir)
    return dirs


def _resolve_written_wii_save(since: float) -> Optional[str]:
    """The Wii title ``data/`` folder actually written this session, or None.

    Conservative like _resolve_written_save: no write since *since* means
    nothing to adopt (silent no-op — the game may not have saved this
    session). Exactly one title folder touched is the answer. More than one
    touched folder is ambiguous — we can't tell which game it was actually
    for, so nothing is adopted and a warning is surfaced (#431) rather than
    guessing wrong and syncing one game's save under another's slug.
    """
    touched = [
        d for d in _wii_title_data_dirs()
        if any(_mtime(f) >= since for f in d.rglob("*") if f.is_file())
    ]
    if not touched:
        return None
    if len(touched) > 1:
        names = ", ".join(d.parent.name for d in touched)
        click.echo(
            f"Warning: multiple Wii titles wrote saves this session ({names}) — "
            f"can't tell which one belongs to this game, skipping save sync.",
            err=True,
        )
        return None
    return str(touched[0])
