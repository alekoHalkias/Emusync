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

import os
from pathlib import Path
from typing import Optional

import click

from cli.detect import _SWITCH_TITLE_ID_RE
from cli.run_reconcile import _mtime

# Native + flatpak Eden NAND roots (mirrors _WII_NAND_ROOTS in cli/run_wii.py).
# Eden has no Flathub package yet (AppImage-only), so there's no flatpak root —
# but EmuDeck-managed installs (common on Steam Deck) redirect Eden's whole
# data directory to ~/Emulation/storage/eden/ instead of the XDG default, so
# both roots are checked the same way native/flatpak both are for every other
# standalone emulator (#441).
_SWITCH_NAND_ROOTS = (
    Path.home() / ".local/share/eden/nand/user/save/0000000000000000",
    Path.home() / "Emulation/storage/eden/nand/user/save/0000000000000000",
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


def _switch_title_id_from_rom(rom_path: str) -> Optional[str]:
    """The 16-hex title ID bracketed in *rom_path*'s filename, or None.

    Same scene convention _SWITCH_TITLE_ID_RE already filters base/update/DLC
    files with (cli/detect.py, #419) — reused here because it's also the
    title-ID folder name under each Eden profile, letting a save be pre-seeded
    to its exact destination without ever having played the game (#443). A
    filename without the tag returns None; the caller falls back to the
    existing blind-first-play/learn behavior.
    """
    match = _SWITCH_TITLE_ID_RE.search(os.path.basename(rom_path))
    return match.group(1) if match else None


def _seed_switch_save(save_client, save_key: str, rom_path: str) -> list[str]:
    """Pre-seed the server's existing save into every profile folder that
    already exists on this device, before the game is ever launched here.

    Without this, a device's first-ever session for a learned-save-path game
    plays blind (the destination folder isn't known until after that session),
    discarding any progress already synced from another device (#443). Since
    the title-ID part of the destination IS derivable up front (unlike the
    emulator-generated profile-ID part), seeding every existing profile now
    means whichever one the player actually picks in Eden already has the
    synced save — _resolve_written_switch_save still works unchanged
    afterward, since seeded files get an mtime before the session starts and
    only the profile actually played gets touched during play.

    Returns the destination paths actually seeded (empty if the title ID
    can't be derived from the filename, or no profile folder exists yet).
    """
    title_id = _switch_title_id_from_rom(rom_path)
    if not title_id:
        return []
    seeded = []
    for profile_dir in _switch_profile_dirs():
        dest = profile_dir / title_id
        try:
            pulled, _ = save_client.pull_save(save_key, str(dest))
        except Exception:
            continue
        if pulled:
            seeded.append(str(dest))
    return seeded
