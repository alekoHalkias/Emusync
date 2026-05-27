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
    return SyncClient(host, cfg.server_port, cfg.server_pin, cfg.device_id, cfg.device_name)


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _get_device_name(client: SyncClient, device_id: str) -> str:
    """Return the display name for a device ID, or the ID itself as fallback."""
    try:
        devices = client.list_devices()
        for d in devices:
            if d.get("id") == device_id:
                return d.get("name", device_id)
    except Exception:
        pass
    return device_id


def _show_game_running_popup(game_name: str, device_name: str) -> None:
    """Show a blocking 'game already running' dialog using the best available method.

    Tries zenity → kdialog → xmessage (all Wayland-safe) before falling back to
    tkinter, so it works even when libtk is missing or X11 is unavailable.
    """
    msg = f"{game_name} is already running.\nPlease close it on {device_name}."

    cmds = [
        # notify-send is non-blocking but works inside gamescope (Steam Deck Gaming Mode)
        # where zenity/kdialog cannot create windows; run it and also continue to a
        # blocking dialog so the user sees a modal on desktop environments too.
        ["notify-send", "--app-name=EmuSync", "--urgency=normal", "EmuSync", msg],
        ["zenity", "--info", "--title=EmuSync", f"--text={msg}", "--width=360", "--no-wrap"],
        ["kdialog", "--msgbox", msg, "--title", "EmuSync"],
        ["xmessage", "-center", "-buttons", "OK:0", msg],
    ]
    notify_sent = False
    for cmd in cmds:
        is_notify = cmd[0] == "notify-send"
        try:
            subprocess.run(cmd, timeout=300)
            if is_notify:
                notify_sent = True
                continue  # always try a blocking dialog after notifying
            return
        except (FileNotFoundError, PermissionError):
            continue
        except subprocess.TimeoutExpired:
            if not is_notify:
                return

    # Last-resort tkinter (may fail on systems without libtk)
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        messagebox.showinfo("EmuSync", msg, parent=root)
        root.destroy()
    except Exception:
        pass


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
    import threading
    import uvicorn
    from server.store import Store
    from server import api as api_module
    from server import mdns as mdns_module

    cfg = cfg_module.load()
    # Only write config if is_server isn't already set (avoid unnecessary disk write)
    if not cfg.is_server:
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

    # Print token immediately so Electron can resolve server.start() without
    # waiting for mDNS registration (which can take several hundred ms).
    click.echo(f"Pairing token: {master_token}")
    sys.stdout.flush()
    click.echo(f"EmuSync server running on :{cfg.server_port}")

    # Advertise via mDNS in a background thread so it doesn't block uvicorn startup.
    zc = None
    info = None
    _mdns_lock = threading.Lock()

    def _advertise_mdns() -> None:
        nonlocal zc, info
        try:
            _zc, _info = mdns_module.advertise(cfg.device_name, cfg.server_port)
            with _mdns_lock:
                zc, info = _zc, _info
        except Exception as e:
            click.echo(
                f"Warning: mDNS registration failed ({e}). Server will work without LAN discovery.",
                err=True,
            )

    mdns_thread = threading.Thread(target=_advertise_mdns, daemon=True)
    mdns_thread.start()

    try:
        uvicorn.run(api_module.app, host="0.0.0.0", port=cfg.server_port, log_level="warning")
    finally:
        mdns_thread.join(timeout=2)
        with _mdns_lock:
            if zc and info:
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


@device.command("connect")
@click.option("--host", default=None, help="Server host (auto-discovered via mDNS if omitted)")
@click.option("--port", default=None, type=int, help="Server port (default: 8765)")
@click.option("--pin", default="", help="Server PIN (leave blank for open servers)")
def device_connect(host: str | None, port: int | None, pin: str) -> None:
    """Connect this device to an EmuSync server."""
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
    # Verify we can authenticate with the given PIN before saving
    client = SyncClient(host, port, pin, cfg.device_id, cfg.device_name)
    try:
        devices = client.list_devices()
        click.echo(f"Connected — {len(devices)} device(s) on server.")
    except Exception as e:
        click.echo(f"Connection failed: {e}", err=True)
        sys.exit(1)
    cfg.server_host = host
    cfg.server_port = port
    cfg.server_pin = pin
    cfg_module.save(cfg)
    click.echo("Connected. Settings saved to ~/.emusync/emusync.toml")


@device.command("list")
def device_list() -> None:
    """List all paired devices."""
    devices = _client().list_devices()
    click.echo(f"{'ID':<36}  Name")
    click.echo("-" * 55)
    for d in devices:
        click.echo(f"{d['id']:<36}  {d['name']}")


@device.command("compare")
def device_compare() -> None:
    """Compare game coverage between this device and other paired devices."""
    cfg = cfg_module.load()
    client = _client(cfg)

    if not client.health():
        click.echo(
            "Cannot reach EmuSync server. Is it running on your gaming PC?",
            err=True,
        )
        sys.exit(1)

    games = client.list_games()
    if not games:
        click.echo("No games managed. Use 'emusync game add' to add one.")
        return

    my_id = cfg.device_id
    my_name = cfg.device_name or my_id

    # Fetch per-game device lists once, in parallel-ish (sequential — no async here)
    game_devs: dict[str, list[dict]] = {}
    for g in games:
        try:
            game_devs[g["slug"]] = client.list_game_devices(g["slug"])
        except Exception:
            game_devs[g["slug"]] = []

    # Partition into: on this device / missing from this device
    mine: list[tuple[str, list[str]]] = []      # (game_name, [other_device_names])
    missing: list[tuple[str, list[str]]] = []   # (game_name, [device_names_that_have_it])

    for g in games:
        devs = game_devs[g["slug"]]
        ids = {d["id"] for d in devs}
        if my_id in ids:
            others = [d["name"] for d in devs if d["id"] != my_id]
            mine.append((g["name"], others))
        else:
            others = [d["name"] for d in devs]
            if others:
                missing.append((g["name"], others))

    click.echo(f"\nDevice: {my_name}  (this device)\n")

    if mine:
        click.echo("Games on this device")
        w = max(len(n) for n, _ in mine)
        for name, others in mine:
            suffix = f"also on: {', '.join(others)}" if others else "only on this device"
            click.echo(f"  {name:<{w}}   {suffix}")

    if missing:
        click.echo("\nMissing from this device")
        w = max(len(n) for n, _ in missing)
        for name, others in missing:
            click.echo(f"  {name:<{w}}   on: {', '.join(others)}")

    if not mine and not missing:
        click.echo("No games found on any device.")
    elif not missing:
        click.echo("\n✓ All server games are installed on this device.")


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

def _find_save_or_state_file(configured_path: str) -> str | None:
  """Look for save/state files with different extensions. Return path if found, None if not."""
  if not configured_path:
    return None
  p = Path(configured_path)
  if p.exists():
    return configured_path
  # Look for files with same name but different extension in the same directory
  dir_path = p.parent
  base_name = p.stem  # filename without extension
  if dir_path.exists():
    for f in dir_path.iterdir():
      if f.is_file() and f.stem == base_name:
        return str(f)
  return None


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

    # Block duplicate launches before attempting to acquire the lock
    try:
        lock_info = client.get_lock(game_slug)
        if lock_info.get("locked"):
            game_data = client.get_game(game_slug)
            name = game_data["name"] if game_data else game_slug
            locking_device = lock_info.get("device_id", "")
            if locking_device == cfg.device_id:
                device_name = cfg.device_name
            else:
                device_name = _get_device_name(client, locking_device)
            _show_game_running_popup(name, device_name)
            sys.exit(0)
    except Exception:
        pass  # can't reach server yet; let acquire_lock report the real error

    try:
        client.acquire_lock(game_slug)
    except ValueError:
        # Lock was acquired by another device between our check and the acquire attempt
        try:
            lock_info = client.get_lock(game_slug)
            game_data = client.get_game(game_slug)
            name = game_data["name"] if game_data else game_slug
            locking_device = lock_info.get("device_id", "")
            device_name = cfg.device_name if locking_device == cfg.device_id else _get_device_name(client, locking_device)
            _show_game_running_popup(name, device_name)
        except Exception:
            pass
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

        # Pull state if configured
        state_path = gd.state_path
        server_state_hash = None
        if state_path:
            pulled, server_state_hash = client.pull_state(game_slug, state_path)
            if pulled:
                click.echo(f"Pulled state for {game_slug}.")

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

        # Check if save/state files were created with different extensions and update config
        actual_save_path = _find_save_or_state_file(save_path)
        actual_state_path = _find_save_or_state_file(state_path) if state_path else None

        if (actual_save_path and actual_save_path != save_path) or (actual_state_path and actual_state_path != state_path):
          try:
            updated_gd = GameDeviceConfig(
              rom_path=gd.rom_path,
              save_path=actual_save_path or save_path,
              launch_command=gd.launch_command,
              state_path=actual_state_path or state_path,
            )
            client.set_game_device(game_slug, updated_gd)
            if actual_save_path and actual_save_path != save_path:
              save_path = actual_save_path
              click.echo(f"Updated save path to {save_path}")
            if actual_state_path and actual_state_path != state_path:
              state_path = actual_state_path
              click.echo(f"Updated state path to {state_path}")
          except Exception as exc:
            click.echo(f"Warning: failed to update save/state paths: {exc}", err=True)

        if Path(save_path).exists():
            local_hash = hashlib.sha256(Path(save_path).read_bytes()).hexdigest()
            if local_hash != server_hash:
                try:
                    client.push_save(game_slug, save_path)
                    click.echo(f"Pushed save for {game_slug}.")
                except Exception as exc:
                    click.echo(f"Warning: failed to push save: {exc}", err=True)

        # Push state if configured
        if state_path and Path(state_path).exists():
            local_state_hash = hashlib.sha256(Path(state_path).read_bytes()).hexdigest()
            if local_state_hash != server_state_hash:
                try:
                    client.push_state(game_slug, state_path)
                    click.echo(f"Pushed state for {game_slug}.")
                except Exception as exc:
                    click.echo(f"Warning: failed to push state: {exc}", err=True)
    finally:
        _release()
        game_pid_file.unlink(missing_ok=True)

    sys.exit(exit_code if "exit_code" in dir() else 0)


if __name__ == "__main__":
    cli()
