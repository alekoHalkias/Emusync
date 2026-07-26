"""`emusync update` — manage Switch update/DLC files under their game (#441).

Eden has no headless install path for update/DLC .nsp files (GUI-only "File >
Install Files to NAND", requiring the user's own prod.keys), and its installed
content lives in one shared content-addressed NAND store, not a per-title
folder, so it can't be synced like a save/state. Instead this manages the
not-yet-installed files themselves: added into a managed per-game folder,
pushed to other devices via the same rom-transfer pipe ROMs use (tagged
kind='update' so the receiving side never touches the game's rom_path) — the
one remaining manual step per device is Eden's own NAND install.
"""
from __future__ import annotations

import os
import shutil
import sys

import click

import server.config as cfg_module

from cli.common import _client
from cli.root import cli
from cli.transfer import switch_updates_dir


@cli.group("update")
def update() -> None:
    """Manage Switch update/DLC files for a game."""


def _require_client(cfg):
    if not cfg.server_host and not cfg.is_server:
        click.echo("EmuSync is not configured. Run 'emusync device connect' first.", err=True)
        sys.exit(1)
    client = _client(cfg)
    if not client.health():
        click.echo("Cannot reach EmuSync server. Is it running?", err=True)
        sys.exit(1)
    return client


def _require_game(client, slug: str) -> dict:
    game = client.get_game(slug)
    if not game:
        click.echo(f"No game with slug '{slug}'. Run 'emusync game list' to see slugs.", err=True)
        sys.exit(1)
    return game


@update.command("add")
@click.argument("slug")
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
def add_update(slug: str, file: str) -> None:
    """Copy an update/DLC .nsp/.xci file into SLUG's managed updates folder."""
    cfg = cfg_module.load()
    client = _require_client(cfg)
    _require_game(client, slug)

    dest_dir = switch_updates_dir(cfg.data_dir, slug)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, os.path.basename(file))
    if os.path.abspath(dest) == os.path.abspath(file):
        click.echo(f"'{file}' is already in the managed folder.")
        return
    shutil.copyfile(file, dest)
    click.echo(f"Added {os.path.basename(file)} to {dest_dir}")


@update.command("list")
@click.argument("slug")
def list_updates(slug: str) -> None:
    """List update/DLC files managed for SLUG on this device."""
    cfg = cfg_module.load()
    client = _require_client(cfg)
    _require_game(client, slug)

    dest_dir = switch_updates_dir(cfg.data_dir, slug)
    if not os.path.isdir(dest_dir):
        click.echo("No update files managed for this game yet.")
        return
    files = sorted(os.listdir(dest_dir))
    if not files:
        click.echo("No update files managed for this game yet.")
        return
    for name in files:
        size_mb = os.path.getsize(os.path.join(dest_dir, name)) / (1024 * 1024)
        click.echo(f"  {name}  ({size_mb:.1f} MB)")


@update.command("push")
@click.argument("slug")
@click.argument("filename")
def push_update(slug: str, filename: str) -> None:
    """Push a managed update/DLC file for SLUG to another device."""
    cfg = cfg_module.load()
    client = _require_client(cfg)
    _require_game(client, slug)

    dest_dir = switch_updates_dir(cfg.data_dir, slug)
    local_path = os.path.join(dest_dir, filename)
    if not os.path.isfile(local_path):
        click.echo(f"'{filename}' is not in this device's managed folder for '{slug}'.", err=True)
        click.echo(f"Run 'emusync update list {slug}' to see what's available.", err=True)
        sys.exit(1)

    try:
        devices = client.list_devices()
    except Exception as e:
        click.echo(f"Failed to fetch devices: {e}", err=True)
        sys.exit(1)

    others = [d for d in devices if d["id"] != cfg.device_id]
    if not others:
        click.echo("No other devices paired. Connect another device first.")
        return

    click.echo("\nAvailable devices:")
    for i, d in enumerate(others, 1):
        status = " (online)" if d.get("is_online") else " (offline)"
        click.echo(f"  {i}. {d['name']}{status}")

    target_idx = click.prompt("Select target device", type=int) - 1
    if not (0 <= target_idx < len(others)):
        click.echo("Invalid selection.", err=True)
        sys.exit(1)
    target = others[target_idx]

    file_mb = os.path.getsize(local_path) / (1024 * 1024)
    click.echo(f"Uploading {filename} ({file_mb:.1f} MB)...")
    try:
        # destination_path here is only a filename hint — the receiving
        # device always lands it in its own managed folder, never a
        # sender-supplied absolute path (#441).
        result = client.create_rom_transfer(slug, target["id"], filename, local_path, kind="update")
    except Exception as e:
        click.echo(f"Failed: {e}", err=True)
        sys.exit(1)

    if result.get("target_online"):
        click.echo(f"Pushed to {target['name']} — will land in its managed updates folder shortly.")
    else:
        click.echo(f"Warning: {target['name']} is offline — will be delivered when it comes online.")
