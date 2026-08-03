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

from cli.detect import _switch_title_id_from_rom  # noqa: F401 — re-exported for existing callers/tests
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

# Eden's mod folder, one sibling directory up from nand/ (issue #444): each
# installed mod for a title lives in its own subfolder under
# load/<title-id-hex>/<mod-name>/. Same dual-root story as the NAND save roots.
_SWITCH_LOAD_ROOTS = (
    Path.home() / ".local/share/eden/load",
    Path.home() / "Emulation/storage/eden/load",
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


def _find_local_switch_save(title_id: str) -> Optional[str]:
    """A title-ID folder matching *title_id* that already exists locally and
    has real data in it, across every profile, or None (#443).

    Matching by the (stable, per-game) title ID directly — rather than only
    ever guessing from "what got touched since launch" — means a device that
    has already played this game once finds its own save deterministically on
    every subsequent launch, with no dependence on mtimes or on exactly one
    title folder having changed this session. An empty/never-written folder
    (e.g. one this device seeded but never actually got played) doesn't count
    as "found" — nothing to reconcile against yet.
    """
    for profile_dir in _switch_profile_dirs():
        candidate = profile_dir / title_id
        if candidate.is_dir() and any(f.is_file() for f in candidate.rglob("*")):
            return str(candidate)
    return None


def _seed_switch_save(save_client, save_key: str, title_id: str) -> list[str]:
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

    Returns the destination paths actually seeded (empty if *title_id* is
    blank, or no profile folder exists yet).
    """
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


# ── communal mod pool (issue #444) ─────────────────────────────────────────────

def _local_switch_mods(title_id: str) -> dict[str, Path]:
    """Every mod subfolder already on this device for *title_id*, name → path.

    Checks both load roots; the first root that has a given mod name wins on
    the rare chance both exist (shouldn't normally happen — a device only
    really has one active Eden data directory).
    """
    mods: dict[str, Path] = {}
    for root in _SWITCH_LOAD_ROOTS:
        title_dir = root / title_id
        if not title_dir.is_dir():
            continue
        for mod_dir in title_dir.iterdir():
            if mod_dir.is_dir() and mod_dir.name not in mods:
                mods[mod_dir.name] = mod_dir
    return mods


def _switch_load_root_for(title_id: str) -> Path:
    """Which load root a newly-pulled mod for *title_id* should land under.

    Prefers a root that already has this title's folder (so new mods land
    next to existing ones), then any root that exists at all, then the
    primary root as a last resort (created on first pull).
    """
    for root in _SWITCH_LOAD_ROOTS:
        if (root / title_id).is_dir():
            return root
    for root in _SWITCH_LOAD_ROOTS:
        if root.is_dir():
            return root
    return _SWITCH_LOAD_ROOTS[0]


def _sync_switch_mods(client, title_id: str) -> tuple[list[str], list[str]]:
    """Lightweight, name-only mod sync: push local mods missing from the
    communal pool, pull pool mods missing locally (#444).

    Deliberately never re-verifies content for a mod that already exists by
    name on both sides — mod folders can be gigabytes (1.4GB seen in
    practice), so re-hashing/re-transferring on every launch isn't
    reasonable. Best-effort throughout: any failure here must never block a
    game launch, so every step is swallowed rather than raised.
    """
    if not title_id:
        return [], []
    try:
        local = _local_switch_mods(title_id)
        pool_names = {m["mod_name"] for m in client.list_switch_mods(title_id)}
    except Exception:
        return [], []

    pushed: list[str] = []
    for name, folder in local.items():
        if name in pool_names:
            continue
        try:
            client.push_switch_mod(title_id, name, str(folder))
            pushed.append(name)
        except Exception:
            continue

    pulled: list[str] = []
    dest_root = _switch_load_root_for(title_id)
    for name in pool_names - local.keys():
        try:
            if client.pull_switch_mod(title_id, name, str(dest_root / title_id / name)):
                pulled.append(name)
        except Exception:
            continue

    return pushed, pulled
