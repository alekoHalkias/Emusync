"""RPCS3 per-title save adapter for `emusync run` (issue #422).

RPCS3 keeps saves as one folder per title under
``dev_hdd0/home/00000001/savedata/<TITLE_ID>…/``. The folder isn't knowable at
import time, so it's learned after a session like Wii's (cli/run_wii.py).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import click

from cli.run_reconcile import _mtime

_SAVEDATA_SUFFIX = "dev_hdd0/home/00000001/savedata"
# Native, flatpak, and EmuDeck-redirected data dirs.
_PS3_SAVE_ROOTS = (
    Path.home() / ".config/rpcs3" / _SAVEDATA_SUFFIX,
    Path.home() / ".var/app/net.rpcs3.RPCS3/config/rpcs3" / _SAVEDATA_SUFFIX,
    Path.home() / "Emulation/storage/rpcs3" / _SAVEDATA_SUFFIX,
)


def _resolve_written_ps3_save(since: float) -> Optional[str]:
    """The single savedata title folder written this session, or None.

    More than one touched folder is ambiguous — warn and adopt nothing rather
    than sync one game's save under another's slug.
    """
    touched = [
        d for root in _PS3_SAVE_ROOTS if root.is_dir()
        for d in root.iterdir()
        if d.is_dir() and any(_mtime(f) >= since for f in d.rglob("*") if f.is_file())
    ]
    if not touched:
        return None
    if len(touched) > 1:
        click.echo(
            f"Warning: multiple PS3 save folders were written this session "
            f"({', '.join(d.name for d in touched)}) — can't tell which belongs "
            f"to this game, skipping save sync.",
            err=True,
        )
        return None
    return str(touched[0])
