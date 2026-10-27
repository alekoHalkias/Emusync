"""`emusync rom` — manage on-demand local copies of network-sourced ROMs (issue #255).

`rom localize` copies a ROM from its network master onto local disk so it can be
played off-network; `rom delocalize` removes that local copy to reclaim space.
Saves/states are untouched — only the ROM file is copied. The network master is
never modified or deleted.
"""
from __future__ import annotations

import os
import sys

import click

import server.config as cfg_module
from server.sync_client import GameDeviceConfig

from cli import netrom
from cli.common import _client
from cli.root import cli
from cli.transfer import _parse_selection


@cli.group("rom")
def rom() -> None:
    """Manage local copies of network-sourced ROMs."""


def _require_client(cfg):
    if not cfg.server_host and not cfg.is_server:
        click.echo("EmuSync is not configured. Run 'emusync device connect' first.", err=True)
        sys.exit(1)
    client = _client(cfg)
    if not client.health():
        click.echo("Cannot reach EmuSync server. Is it running?", err=True)
        sys.exit(1)
    return client


def _network_games(client) -> list[dict]:
    """This device's games whose ROM lives on a network share."""
    try:
        games = client.list_my_game_devices()
    except Exception as e:
        click.echo(f"Failed to fetch games: {e}", err=True)
        sys.exit(1)
    return [g for g in games if g.get("rom_source") == "network"]


def _local_dest_for(client, cfg, game: dict, gd: GameDeviceConfig, dest: str) -> str:
    """Resolve where a localized copy should be written.

    Precedence: an explicit ``--dest`` folder, then a destination already stored
    on the game, then the console's configured local folder. The rel-path (or the
    ROM basename) is appended so per-game files don't collide.
    """
    rel = gd.rom_rel_path or os.path.basename(gd.rom_path)
    if dest:
        return os.path.join(dest, *netrom.sanitize_rel_path(rel).split("/"))
    if gd.local_rom_path:
        return gd.local_rom_path
    # Fall back to the console's local folder (set during import).
    try:
        consoles = client.get_device_consoles(cfg.device_id)
    except Exception:
        consoles = []
    folder = next(
        (c.get("device_local_folder") for c in consoles
         if c.get("console_name") == game.get("console") and c.get("device_local_folder")),
        "",
    )
    if not folder:
        click.echo(
            f"  No local destination for '{game['name']}'. Set the console's local "
            f"folder in the import wizard, or pass --dest <folder>.",
            err=True,
        )
        return ""
    return os.path.join(folder, *netrom.sanitize_rel_path(rel).split("/"))


@rom.command("list")
def rom_list() -> None:
    """Show this device's network ROMs and whether a local copy exists."""
    cfg = cfg_module.load()
    client = _require_client(cfg)
    games = _network_games(client)
    if not games:
        click.echo("No network-sourced ROMs on this device.")
        return
    click.echo("\nNetwork ROMs:")
    for g in games:
        local = g.get("local_rom_path") or ""
        state = "💾 local" if local and os.path.isfile(local) else "🌐 network-only"
        click.echo(f"  {state:<16} {g['name']}  —  {g.get('rom_rel_path') or os.path.basename(g.get('rom_path',''))}")


def _select_games(games: list[dict], slug: str, console: str, verb: str) -> list[dict]:
    """Resolve which games to act on from a slug, a --console filter, or a prompt."""
    if slug:
        match = [g for g in games if g["slug"] == slug]
        if not match:
            click.echo(f"'{slug}' is not a network-sourced ROM on this device.", err=True)
            sys.exit(1)
        return match
    if console:
        match = [g for g in games if g.get("console") == console]
        if not match:
            click.echo(f"No network ROMs for console '{console}'.", err=True)
            sys.exit(1)
        return match
    click.echo(f"\nGames available to {verb}:")
    for i, g in enumerate(games, 1):
        click.echo(f"  {i:>3}. {g['name']}  ({g.get('console','')})")
    raw = click.prompt(f"\nSelect games to {verb} (e.g. 1  or  1,3  or  1-4)")
    chosen = _parse_selection(raw, len(games))
    if not chosen:
        click.echo("No valid selection.", err=True)
        sys.exit(1)
    return [games[i] for i in chosen]


@rom.command("localize")
@click.argument("slug", required=False)
@click.option("--console", default="", help="Localize every network ROM for this console.")
@click.option("--dest", default="", help="Override the local destination folder.")
def rom_localize(slug: str, console: str, dest: str) -> None:
    """Copy a network ROM (or a whole console) onto local disk for offline play."""
    cfg = cfg_module.load()
    client = _require_client(cfg)
    games = _network_games(client)
    if not games:
        click.echo("No network-sourced ROMs on this device.")
        return
    targets = _select_games(games, slug, console, "localize")

    ok, failed = 0, []
    for game in targets:
        gd = client.get_game_device(game["slug"])
        if not gd:
            failed.append((game["name"], "no device config"))
            continue
        local_path = _local_dest_for(client, cfg, game, gd, dest)
        if not local_path:
            failed.append((game["name"], "no local destination"))
            continue
        click.echo(f"\n── {game['name']} ──")
        try:
            master_hash = netrom.localize_rom(gd.rom_path, local_path)
        except netrom.LocalizeError as exc:
            click.echo(f"  ✗ {exc}", err=True)
            failed.append((game["name"], str(exc)))
            continue
        gd.local_rom_path = local_path
        gd.rom_sha256 = master_hash
        try:
            client.set_game_device(game["slug"], gd)
        except Exception as exc:
            failed.append((game["name"], f"copied but config update failed: {exc}"))
            continue
        click.echo(f"  ✓ localized → {local_path}")
        ok += 1

    click.echo(f"\nLocalized {ok} ROM(s).")
    if failed:
        click.echo(f"{len(failed)} failed:", err=True)
        for name, reason in failed:
            click.echo(f"  - {name}: {reason}", err=True)
        sys.exit(1)


@rom.command("delocalize")
@click.argument("slug", required=False)
@click.option("--console", default="", help="Delocalize every network ROM for this console.")
def rom_delocalize(slug: str, console: str) -> None:
    """Remove the local copy of a network ROM (the network master is kept)."""
    cfg = cfg_module.load()
    client = _require_client(cfg)
    games = [g for g in _network_games(client) if g.get("local_rom_path")]
    if not games:
        click.echo("No localized network ROMs on this device.")
        return
    targets = _select_games(games, slug, console, "delocalize")

    removed = 0
    for game in targets:
        gd = client.get_game_device(game["slug"])
        if not gd or not gd.local_rom_path:
            continue
        try:
            netrom.delocalize_rom(gd.local_rom_path, gd.rom_path)
        except netrom.LocalizeError as exc:
            click.echo(f"  ✗ {game['name']}: {exc}", err=True)
            continue
        gd.local_rom_path = ""
        gd.rom_sha256 = ""
        try:
            client.set_game_device(game["slug"], gd)
        except Exception as exc:
            click.echo(f"  ✗ {game['name']}: removed copy but config update failed: {exc}", err=True)
            continue
        click.echo(f"  ✓ removed local copy of {game['name']}")
        removed += 1

    click.echo(f"\nDelocalized {removed} ROM(s).")
