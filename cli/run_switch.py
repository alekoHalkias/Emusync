"""Switch per-title save adapter for `emusync run` (issue #419).

Eden (the maintained Yuzu-lineage fork) emulates the Switch's NAND as a real
directory tree: ``nand/user/save/0000000000000000/<profile-id>/<title-id-hex>/``
holds one folder per installed title's save data, keyed by the game's 16-hex
title ID. ``<profile-id>`` is itself an emulator-generated folder (there's
normally exactly one for a single local profile) that isn't knowable ahead of
time, so — like Wii's title-ID folder (cli/run_wii.py, #431) and 3DS's ID0/ID1
hash dirs (#418) — it's found by probing for whatever already exists rather
than hardcoded.

The title-ID folder itself isn't knowable before the game has been played at
least once, so it's learned the same way Wii's is: after a session, find
whichever title folder was actually written and adopt that path (see
cli/run_reconcile.py's _resolve_written_save for the RetroArch equivalent this
mirrors, and cli/run_wii.py for the Wii sibling this is a near-exact copy of).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import click

from cli.run_reconcile import _mtime

# Native + flatpak Eden NAND roots (mirrors _WII_NAND_ROOTS in cli/run_wii.py).
# Eden has no Flathub package yet (AppImage-only), so there's no flatpak root.
_SWITCH_NAND_ROOTS = (
    Path.home() / ".local/share/eden/nand/user/save/0000000000000000",
)


def _switch_profile_dirs() -> list[Path]:
    """Every existing profile-ID folder under each NAND save root."""
    dirs: list[Path] = []
    for root in _SWITCH_NAND_ROOTS:
        if not root.is_dir():
            continue
        dirs.extend(d for d in root.iterdir() if d.is_dir())
    return dirs


def _switch_title_save_dirs() -> list[Path]:
    """Every title's save folder across every discovered profile."""
    return [
        title_dir
        for profile_dir in _switch_profile_dirs()
        for title_dir in profile_dir.iterdir()
        if title_dir.is_dir()
    ]


def _resolve_written_switch_save(since: float) -> Optional[str]:
    """The Switch title save folder actually written this session, or None.

    Conservative like _resolve_written_wii_save: no write since *since* means
    nothing to adopt. Exactly one title folder touched is the answer. More
    than one touched folder is ambiguous — nothing is adopted and a warning is
    surfaced rather than guessing wrong and syncing one game's save under
    another's slug.
    """
    touched = [
        d for d in _switch_title_save_dirs()
        if any(_mtime(f) >= since for f in d.rglob("*") if f.is_file())
    ]
    if not touched:
        return None
    if len(touched) > 1:
        names = ", ".join(d.name for d in touched)
        click.echo(
            f"Warning: multiple Switch titles wrote saves this session ({names}) — "
            f"can't tell which one belongs to this game, skipping save sync.",
            err=True,
        )
        return None
    return str(touched[0])
