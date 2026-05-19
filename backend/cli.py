#!/usr/bin/env python3
import hashlib
import re
import signal
import subprocess
import sys
import threading
import uuid

import click
import httpx
import uvicorn

from emusync import config as cfg_module
from emusync import mdns_service
from emusync import store as store_module
from emusync.server import create_app
from emusync.sync_client import SyncClient


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _hash_file(path: str) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except FileNotFoundError:
        return ""


def _client() -> SyncClient:
    cfg = cfg_module.load()
    if not cfg.token:
        click.echo("Not configured. Run 'emusync device pair' first.", err=True)
        sys.exit(1)
    return SyncClient(cfg.server_host, cfg.server_port, cfg.token)


@click.group()
def cli():
    """EmuSync — LAN save-file sync for emulators."""


# ── server ─────────────────────────────────────────────────────────────────


@cli.group()
def server():
    """Manage the EmuSync server."""


@server.command("start")
def server_start():
    """Start the server and print the pairing token."""
    cfg = cfg_module.load()
    cfg.is_server = True
    cfg_module.save(cfg)

    db = store_module.Store(cfg.data_dir)
    token = str(uuid.uuid4())
    app = create_app(db, token)

    click.echo(f"Pairing token: {token}")
    click.echo(f"EmuSync server running on :{cfg.server_port}")

    stop = threading.Event()
    threading.Thread(
        target=mdns_service.advertise,
        args=(cfg.device_name or "emusync", cfg.server_port, stop),
        daemon=True,
    ).start()

    def _shutdown(sig, frame):
        click.echo("\nShutting down...")
        stop.set()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    uvicorn.run(app, host="0.0.0.0", port=cfg.server_port, log_level="warning")


# ── device ─────────────────────────────────────────────────────────────────


@cli.group()
def device():
    """Manage devices."""


@device.command("pair")
@click.option("--host", default=None, help="Server host (auto-discovered via mDNS if omitted)")
@click.option("--port", default=8765, show_default=True)
@click.option("--token", "master_token", required=True, help="Pairing token shown by server")
def device_pair(host, port, master_token):
    """Pair this device with an EmuSync server."""
    if not host:
        click.echo("Scanning LAN for EmuSync servers...")
        servers = mdns_service.discover(5.0)
        if not servers:
            click.echo("No servers found. Is EmuSync running on your gaming PC?", err=True)
            sys.exit(1)
        if len(servers) == 1:
            host, port = servers[0].host, servers[0].port
            click.echo(f"Found: {servers[0].name} at {host}:{port}")
        else:
            for i, s in enumerate(servers):
                click.echo(f"  [{i}] {s.name}  {s.host}:{s.port}")
            idx = click.prompt("Select server", type=int, default=0)
            host, port = servers[idx].host, servers[idx].port

    cfg = cfg_module.load()
    client = SyncClient(host, port, "")
    new_token = client.pair(master_token, cfg.device_id, cfg.device_name)
    cfg.server_host = host
    cfg.server_port = port
    cfg.token = new_token
    cfg_module.save(cfg)
    click.echo("Paired successfully. Token saved to ~/.emusync/emusync.toml")


@device.command("list")
def device_list():
    """List all paired devices."""
    devices = _client().list_devices()
    if not devices:
        click.echo("No devices registered.")
        return
    click.echo(f"{'ID':<38}  {'Name'}")
    click.echo("-" * 58)
    for d in devices:
        click.echo(f"{d['id']:<38}  {d['name']}")


# ── game ───────────────────────────────────────────────────────────────────


@cli.group()
def game():
    """Manage games."""


@game.command("add")
@click.argument("slug", required=False, default=None)
@click.option("--name", required=True)
@click.option("--rom", default="")
@click.option("--save", "save_path", default="")
@click.option("--command", "launch_command", default="")
def game_add(slug, name, rom, save_path, launch_command):
    """Add a game to EmuSync."""
    if not slug:
        slug = _slug(name)
    c = _client()
    c.add_game(slug, name)
    if rom or save_path or launch_command:
        c.set_game_device(slug, rom, save_path, launch_command)
    click.echo(f"Added '{name}' (slug: {slug})")


@game.command("list")
def game_list():
    """List all games."""
    c = _client()
    games = c.list_games()
    if not games:
        click.echo("No games registered.")
        return
    click.echo(f"{'Slug':<22}  {'Name':<30}  Last synced")
    click.echo("-" * 68)
    for g in games:
        meta = c.get_save_meta(g["slug"])
        last = str(meta["created_at"]) if meta else "never"
        click.echo(f"{g['slug']:<22}  {g['name']:<30}  {last}")


@game.command("edit")
@click.argument("slug")
@click.option("--name", default=None)
@click.option("--rom", default=None)
@click.option("--save", "save_path", default=None)
@click.option("--command", "launch_command", default=None)
def game_edit(slug, name, rom, save_path, launch_command):
    """Edit a game's name or per-device paths."""
    c = _client()
    if name:
        httpx.put(
            f"{c.base_url}/games/{slug}",
            json={"name": name},
            headers=c.headers,
            timeout=10,
        ).raise_for_status()
    if any(v is not None for v in (rom, save_path, launch_command)):
        existing = c.get_game_device(slug) or {}
        c.set_game_device(
            slug,
            rom if rom is not None else existing.get("rom_path", ""),
            save_path if save_path is not None else existing.get("save_path", ""),
            launch_command if launch_command is not None else existing.get("launch_command", ""),
        )
    click.echo(f"Updated '{slug}'")


@game.command("remove")
@click.argument("slug")
def game_remove(slug):
    """Remove a game from EmuSync (does NOT delete save files)."""
    c = _client()
    g = c.get_game(slug)
    name = g["name"] if g else slug
    msg = f"Remove '{name}' from EmuSync management? Save file on disk will NOT be deleted."
    if not click.confirm(msg, default=False):
        return
    c.remove_game(slug)
    click.echo(f"Removed '{name}'")


# ── sync ───────────────────────────────────────────────────────────────────


@cli.group()
def sync():
    """Sync utilities."""


@sync.command("status")
def sync_status():
    """Show lock and last-save status for all games."""
    c = _client()
    games = c.list_games()
    if not games:
        click.echo("No games registered.")
        return
    click.echo(f"{'Slug':<22}  {'Name':<25}  {'Lock':<20}  Last save")
    click.echo("-" * 80)
    for g in games:
        lock = c.get_lock(g["slug"])
        lock_str = f"locked ({lock['device_id'][:8]})" if lock.get("locked") else "unlocked"
        meta = c.get_save_meta(g["slug"])
        last = str(meta["created_at"]) if meta else "never"
        click.echo(f"{g['slug']:<22}  {g['name']:<25}  {lock_str:<20}  {last}")


# ── run ────────────────────────────────────────────────────────────────────


@cli.command("run", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
@click.option("--game", "game_slug", required=True)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def run_cmd(game_slug, args):
    """Sync save then launch emulator: emusync run --game zelda -- retroarch ..."""
    cfg = cfg_module.load()
    if not cfg.token:
        click.echo("Not configured. Run 'emusync device pair' first.", err=True)
        sys.exit(1)

    c = SyncClient(cfg.server_host, cfg.server_port, cfg.token)

    if not c.health():
        click.echo("Cannot reach EmuSync server. Is it running on your gaming PC?", err=True)
        sys.exit(1)

    gd = c.get_game_device(game_slug)
    if not gd:
        click.echo(f"Game '{game_slug}' is not configured for this device.", err=True)
        sys.exit(1)

    save_path = gd.get("save_path", "")

    try:
        c.acquire_lock(game_slug)
    except Exception:
        click.echo("This game is currently being played on another device.", err=True)
        sys.exit(1)

    lock_released = False

    def _release():
        nonlocal lock_released
        if not lock_released:
            lock_released = True
            c.release_lock(game_slug)

    try:
        try:
            c.pull_save(game_slug, save_path)
        except Exception as e:
            click.echo(f"Warning: pull save failed: {e}", err=True)

        pre_hash = _hash_file(save_path)

        cmd = [a for a in args if a != "--"]
        if not cmd:
            click.echo("No command provided after --game flag.", err=True)
            sys.exit(1)

        result = subprocess.run(cmd)

        post_hash = _hash_file(save_path)
        if post_hash and post_hash != pre_hash:
            try:
                c.push_save(game_slug, save_path)
            except Exception as e:
                click.echo(f"Warning: push save failed: {e}", err=True)

        sys.exit(result.returncode)
    finally:
        _release()


if __name__ == "__main__":
    cli()
