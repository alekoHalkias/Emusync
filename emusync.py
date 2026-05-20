#!/usr/bin/env python3
"""EmuSync CLI — save-file sync for emulators on a home LAN."""
from __future__ import annotations

import hashlib
import os
import re
import signal
import subprocess
import sys
import random
import time
import uuid
from pathlib import Path

# Track the emulator child process so SIGTERM can kill it before exiting
_child_proc: subprocess.Popen | None = None  # type: ignore[type-arg]


def _sigterm_handler(*_) -> None:
    if _child_proc is not None and _child_proc.poll() is None:
        _child_proc.kill()
    sys.exit(0)


signal.signal(signal.SIGTERM, _sigterm_handler)

import click

# Make sure the project root is on the path when invoked directly
sys.path.insert(0, str(Path(__file__).parent))

import server.config as cfg_module
from server.mdns import discover as mdns_discover
from server.sync_client import GameDeviceConfig, SyncClient


def _client(cfg=None) -> SyncClient:
    if cfg is None:
        cfg = cfg_module.load()
    host = cfg.server_host or "localhost"
    return SyncClient(host, cfg.server_port, cfg.token)


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# ── root ──────────────────────────────────────────────────────────────────────

@click.group()
def cli() -> None:
    """EmuSync — keep game saves in sync across your devices."""


# ── server ────────────────────────────────────────────────────────────────────

@cli.group()
def server() -> None:
    """Manage the EmuSync server."""


@server.command("start")
def server_start() -> None:
    """Start the EmuSync server and print the pairing token."""
    import signal
    import uvicorn
    from server.store import Store
    from server import api as api_module
    from server import mdns as mdns_module

    cfg = cfg_module.load()
    cfg.is_server = True
    cfg_module.save(cfg)

    store = Store(cfg.data_dir)
    master_token = cfg.server_pin
    token_file = Path(cfg.data_dir) / ".server_token"
    pid_file = Path(cfg.data_dir) / ".server_pid"
    token_file.write_text(master_token)
    pid_file.write_text(str(os.getpid()))
    api_module.init(store, master_token)
    store.log_event("server_started")

    click.echo(f"Pairing token: {master_token}")
    sys.stdout.flush()
    click.echo(f"EmuSync server running on :{cfg.server_port}")

    zc, info = mdns_module.advertise(cfg.device_name, cfg.server_port)
    try:
        uvicorn.run(api_module.app, host="0.0.0.0", port=cfg.server_port, log_level="warning")
    finally:
        zc.unregister_service(info)
        zc.close()
        token_file.unlink(missing_ok=True)
        pid_file.unlink(missing_ok=True)


@server.command("clear-devices")
def server_clear_devices() -> None:
    """Remove all paired devices so they must re-pair with the new PIN."""
    from server.store import Store
    cfg = cfg_module.load()
    store = Store(cfg.data_dir)
    store.clear_devices()
    click.echo("All paired devices removed.")


@server.command("discover-json")
def server_discover_json() -> None:
    """Discover EmuSync servers on the LAN and output as JSON."""
    import json
    from server import mdns as mdns_module
    results = mdns_module.discover(timeout=2.0)
    click.echo(json.dumps([{"name": r.name, "host": r.host, "port": r.port} for r in results]))


# ── device ────────────────────────────────────────────────────────────────────

@cli.group()
def device() -> None:
    """Manage device pairing."""


@device.command("pair")
@click.option("--host", default=None, help="Server host (auto-discovered via mDNS if omitted)")
@click.option("--port", default=None, type=int, help="Server port (default: 8765)")
@click.option("--token", required=True, help="Master token printed by 'emusync server start'")
def device_pair(host: str | None, port: int | None, token: str) -> None:
    """Pair this device with an EmuSync server."""
    cfg = cfg_module.load()

    if not host:
        click.echo("Scanning LAN for EmuSync servers (5s)...")
        servers = mdns_discover(5.0)
        if not servers:
            click.echo(
                "No servers found. Make sure 'emusync server start' is running on your other device.\n"
                "Or specify --host manually.",
                err=True,
            )
            sys.exit(1)
        if len(servers) == 1:
            svc = servers[0]
            click.echo(f"Found: EmuSync on {svc.name} ({svc.host}:{svc.port})")
            host, port = svc.host, svc.port
        else:
            for i, s in enumerate(servers):
                click.echo(f"  [{i}] {s.name} — {s.host}:{s.port}")
            idx = click.prompt("Select server", type=int)
            host, port = servers[idx].host, servers[idx].port

    port = port or cfg.server_port
    client = SyncClient(host, port, "")
    new_token = client.pair(token, cfg.device_id, cfg.device_name)
    cfg.server_host = host
    cfg.server_port = port
    cfg.token = new_token
    cfg_module.save(cfg)
    click.echo("Paired successfully. Token saved to ~/.emusync/emusync.toml")


@device.command("list")
def device_list() -> None:
    """List all paired devices."""
    devices = _client().list_devices()
    click.echo(f"{'ID':<36}  Name")
    click.echo("-" * 55)
    for d in devices:
        click.echo(f"{d['id']:<36}  {d['name']}")


# ── game ──────────────────────────────────────────────────────────────────────

@cli.group()
def game() -> None:
    """Manage games."""


@game.command("add")
@click.argument("slug", required=False, default=None)
@click.option("--name", required=True, help="Game display name")
@click.option("--rom", "rom_path", default="", help="Path to ROM file")
@click.option("--save", "save_path", default="", help="Path to save file")
@click.option("--command", "launch_command", default="", help="Launch command template")
def game_add(slug: str | None, name: str, rom_path: str, save_path: str, launch_command: str) -> None:
    """Add a game to EmuSync management."""
    client = _client()
    result = client.add_game(name)
    actual_slug = result["slug"]
    if slug and slug != actual_slug:
        # Allow caller to specify a custom slug by re-registering
        from server.store import Store
        cfg = cfg_module.load()
        store = Store(cfg.data_dir)
        store.add_game(slug, name)
        actual_slug = slug

    if rom_path or save_path or launch_command:
        client.set_game_device(actual_slug, GameDeviceConfig(rom_path=rom_path, save_path=save_path, launch_command=launch_command))

    click.echo(f"Added: {name} (slug: {actual_slug})")


@game.command("list")
def game_list() -> None:
    """List all managed games."""
    games = _client().list_games()
    if not games:
        click.echo("No games added yet. Use 'emusync game add' to add one.")
        return
    click.echo(f"{'Slug':<30}  Name")
    click.echo("-" * 55)
    for g in games:
        click.echo(f"{g['slug']:<30}  {g['name']}")


@game.command("edit")
@click.argument("slug")
@click.option("--name", default=None, help="New display name")
@click.option("--rom", "rom_path", default=None, help="ROM path for this device")
@click.option("--save", "save_path", default=None, help="Save path for this device")
@click.option("--command", "launch_command", default=None, help="Launch command for this device")
def game_edit(slug: str, name: str | None, rom_path: str | None, save_path: str | None, launch_command: str | None) -> None:
    """Edit a game's name or this device's paths."""
    client = _client()

    if name is not None:
        client.update_game(slug, name)

    if any(v is not None for v in [rom_path, save_path, launch_command]):
        existing = client.get_game_device(slug) or GameDeviceConfig()
        updated = GameDeviceConfig(
            rom_path=rom_path if rom_path is not None else existing.rom_path,
            save_path=save_path if save_path is not None else existing.save_path,
            launch_command=launch_command if launch_command is not None else existing.launch_command,
        )
        client.set_game_device(slug, updated)

    click.echo(f"Updated: {slug}")


@game.command("remove")
@click.argument("slug")
def game_remove(slug: str) -> None:
    """Remove a game from EmuSync management (does not delete files)."""
    client = _client()
    game_data = client.get_game(slug)
    if not game_data:
        click.echo(f"Game '{slug}' not found.", err=True)
        sys.exit(1)

    confirmed = click.confirm(
        f"Remove {game_data['name']} from EmuSync management? "
        "Save file on disk will NOT be deleted.",
        default=False,
    )
    if not confirmed:
        click.echo("Cancelled.")
        return

    client.remove_game(slug)
    click.echo(f"Removed: {slug}")


# ── sync ──────────────────────────────────────────────────────────────────────

@cli.group()
def sync() -> None:
    """Sync status and utilities."""


@sync.command("status")
def sync_status() -> None:
    """Show lock and save status for all games."""
    client = _client()
    games = client.list_games()
    if not games:
        click.echo("No games managed.")
        return

    click.echo(f"{'Game':<30}  {'Lock':<22}  Last Push")
    click.echo("-" * 80)
    for g in games:
        slug = g["slug"]
        try:
            lock_info = client.get_lock(slug)
            lock_str = lock_info["device_id"][:20] if lock_info.get("locked") else "free"
        except Exception:
            lock_str = "?"
        try:
            meta = client.get_save_meta(slug)
            push_str = meta["pushed_at"][:19] if meta else "never"
        except Exception:
            push_str = "?"
        click.echo(f"{slug:<30}  {lock_str:<22}  {push_str}")


# ── run ───────────────────────────────────────────────────────────────────────

@cli.command("run")
@click.option("--game", "game_slug", required=True, help="Game slug (from 'emusync game list')")
@click.argument("command", nargs=-1, required=True)
def run_game(game_slug: str, command: tuple[str, ...]) -> None:
    """Pull save, launch emulator, push save. Use as a Steam launch wrapper."""
    cfg = cfg_module.load()

    if not cfg.token:
        click.echo(
            "EmuSync is not configured. Run 'emusync device pair' first.",
            err=True,
        )
        sys.exit(1)

    client = _client(cfg)

    if not client.health():
        click.echo(
            "Cannot reach EmuSync server. Is it running on your gaming PC?",
            err=True,
        )
        sys.exit(1)

    gd = client.get_game_device(game_slug)
    if not gd or not gd.save_path:
        click.echo(
            f"No save path configured for '{game_slug}'. "
            f"Run 'emusync game edit {game_slug} --save <path>' first.",
            err=True,
        )
        sys.exit(1)

    save_path = gd.save_path
    game_pid_file = Path(cfg.data_dir) / ".game_pid"

    # Block duplicate launches: if this device already holds the lock, wait up to 5s for it to clear
    try:
        lock_info = client.get_lock(game_slug)
        if lock_info.get("locked") and lock_info.get("device_id") == cfg.device_id:
            click.echo(f"'{game_slug}' is already running on this device. Waiting for it to close...", err=True)
            for _ in range(10):
                time.sleep(0.5)
                lock_info = client.get_lock(game_slug)
                if not lock_info.get("locked"):
                    break
            else:
                click.echo(f"'{game_slug}' is still running. Close it before launching again.", err=True)
                sys.exit(1)
    except Exception:
        pass  # can't reach server yet; let acquire_lock report the real error

    try:
        client.acquire_lock(game_slug)
    except ValueError as exc:
        click.echo(f"This game is currently being played on another device: {exc}", err=True)
        sys.exit(1)

    lock_released = False

    def _release() -> None:
        nonlocal lock_released
        if lock_released:
            return
        try:
            client.release_lock(game_slug)
        except Exception as exc:
            click.echo(f"Warning: failed to release lock: {exc}", err=True)
        lock_released = True

    game_pid_file.write_text(str(os.getpid()))
    try:
        pulled, server_hash = client.pull_save(game_slug, save_path)
        if pulled:
            click.echo(f"Pulled save for {game_slug}.")

        try:
            global _child_proc
            _child_proc = subprocess.Popen(list(command))
            game_pid_file.write_text(f"{os.getpid()}\n{_child_proc.pid}")
            exit_code = _child_proc.wait()
            _child_proc = None
        except Exception as exc:
            click.echo(f"Emulator error: {exc}", err=True)
            _release()
            sys.exit(1)

        if Path(save_path).exists():
            local_hash = hashlib.sha256(Path(save_path).read_bytes()).hexdigest()
            if local_hash != server_hash:
                try:
                    client.push_save(game_slug, save_path)
                    click.echo(f"Pushed save for {game_slug}.")
                except Exception as exc:
                    click.echo(f"Warning: failed to push save: {exc}", err=True)
    finally:
        _release()
        game_pid_file.unlink(missing_ok=True)

    sys.exit(exit_code if "exit_code" in dir() else 0)


if __name__ == "__main__":
    cli()
