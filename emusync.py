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


def _is_server_running(data_dir: str) -> tuple[bool, int | None]:
    """Check if a server is already running on this device.

    Returns (is_running, pid) where pid is the process ID if running, else None.
    """
    pid_file = Path(data_dir) / ".server_pid"
    if not pid_file.exists():
        return False, None

    try:
        pid = int(pid_file.read_text().strip())
        # Check if process exists by sending signal 0 (no-op)
        os.kill(pid, 0)
        return True, pid
    except (ValueError, FileNotFoundError, ProcessLookupError):
        # File doesn't exist, is invalid, or process is gone
        pid_file.unlink(missing_ok=True)
        return False, None


def _initialize_server_interactive(cfg: cfg_module.Config) -> cfg_module.Config:
    """Interactively initialize the server with user input.

    Prompts the user to set a PIN and confirm the port. Returns updated config.
    """
    click.echo("\n" + "=" * 60)
    click.echo("EmuSync Server Initialization")
    click.echo("=" * 60)
    click.echo(f"Device name: {cfg.device_name}")
    click.echo(f"Data directory: {cfg.data_dir}")
    click.echo()

    # Set PIN
    pin = click.prompt(
        "Enter a PIN for this server (leave blank for open access)",
        default="",
        show_default=False,
        type=str,
    ).strip()
    cfg.server_pin = pin

    # Confirm port
    default_port = cfg.server_port
    port_input = click.prompt(
        f"Server port",
        default=default_port,
        type=int,
    )
    cfg.server_port = port_input

    cfg.is_server = True
    cfg_module.save(cfg)

    click.echo("\n✓ Server initialized.")
    click.echo(f"  PIN: {'(open access)' if not pin else '***'}")
    click.echo(f"  Port: {cfg.server_port}")
    click.echo()

    return cfg


def _do_start_server() -> None:
    """Core logic to start the EmuSync server.

    Performs initialization check, duplicate-launch detection, and runs uvicorn.
    """
    import signal
    import threading
    import uvicorn
    from server.store import Store
    from server import api as api_module
    from server import mdns as mdns_module

    cfg = cfg_module.load()

    # Check if server needs initialization
    if not cfg.is_server:
        click.echo("Server not yet initialized on this device.")
        should_init = click.confirm("Initialize now?", default=True)
        if not should_init:
            click.echo("Cancelled.")
            sys.exit(0)
        cfg = _initialize_server_interactive(cfg)

    # Check if server is already running
    is_running, running_pid = _is_server_running(cfg.data_dir)
    if is_running:
        click.echo(f"EmuSync server is already running (PID: {running_pid})")
        click.echo(f"  on :{cfg.server_port}")
        sys.exit(0)

    store = Store(cfg.data_dir)
    master_token = cfg.server_pin
    token_file = Path(cfg.data_dir) / ".server_token"
    pid_file = Path(cfg.data_dir) / ".server_pid"
    token_file.write_text(master_token)
    pid_file.write_text(str(os.getpid()))
    api_module.init(store, master_token, cfg.data_dir)
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


@server.command("start")
def server_start() -> None:
    """Start the EmuSync server and print the pairing token."""
    _do_start_server()


def _do_stop_server() -> None:
    """Core logic to stop the running server process."""
    cfg = cfg_module.load()
    is_running, pid = _is_server_running(cfg.data_dir)

    if not is_running:
        click.echo("server not running")
        return

    try:
        os.kill(pid, signal.SIGKILL)
        click.echo(f"Server (PID {pid}) stopped.")
        # Clean up PID file
        pid_file = Path(cfg.data_dir) / ".server_pid"
        pid_file.unlink(missing_ok=True)
    except ProcessLookupError:
        click.echo("server not running")
        # Clean up stale PID file
        pid_file = Path(cfg.data_dir) / ".server_pid"
        pid_file.unlink(missing_ok=True)
    except Exception as e:
        click.echo(f"Error stopping server: {e}", err=True)


@server.command("stop")
def server_stop() -> None:
    """Stop the running server process."""
    _do_stop_server()


@server.command("restart")
def server_restart() -> None:
    """Stop the running server, then start it again."""
    _do_stop_server()
    click.echo()  # blank line for readability
    _do_start_server()


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
@click.option("--console", "console_name", default="", help="Console name")
def game_add(slug: str | None, name: str, rom_path: str, save_path: str, launch_command: str, console_name: str) -> None:
    """Add a game to EmuSync management."""
    from server.store import Store, Console
    import uuid

    client = _client()
    cfg = cfg_module.load()
    store = Store(cfg.data_dir)

    result = client.add_game(name)
    actual_slug = result["slug"]
    if slug and slug != actual_slug:
        # Allow caller to specify a custom slug by re-registering
        store.add_game(slug, name)
        actual_slug = slug

    if rom_path or save_path or launch_command:
        client.set_game_device(actual_slug, GameDeviceConfig(rom_path=rom_path, save_path=save_path, launch_command=launch_command))

    # Auto-configure console if game has console and paths
    if console_name and (rom_path or save_path):
        device_id = cfg.device_id
        # Extract emulator/core from save path (e.g., mGBA from /path/saves/mGBA/)
        emulator = ""
        game_folder = ""
        save_folder = ""
        state_folder = ""

        if save_path:
            save_dir = os.path.dirname(save_path)
            save_folder = save_dir
            # Try to infer emulator from save folder structure
            emulator = os.path.basename(save_dir)

        if rom_path:
            # Extract console folder by going up 2 levels from ROM file
            # /path/Console/GameFolder/game.rom -> /path/Console/
            rom_file_dir = os.path.dirname(rom_path)
            game_folder = os.path.dirname(rom_file_dir)

        if save_folder:
            # Infer state folder by replacing 'saves' with 'states'
            state_folder = save_folder.replace('saves', 'states')

        # Check if console entry with this exact ROM folder exists
        existing_consoles = store.list_consoles(device_id)
        existing_console = None
        for c in existing_consoles:
            if c.console_name == console_name and c.device_game_folder == game_folder:
                existing_console = c
                break

        if existing_console:
            # Update existing console entry for this ROM folder
            existing_console.device_save_folder = save_folder
            existing_console.device_state_folder = state_folder
            existing_console.device_emulator = emulator
            store.set_console(existing_console)
        else:
            # Create new console entry for this ROM folder
            console_obj = Console(
                id=str(uuid.uuid4()),
                device_id=device_id,
                console_name=console_name,
                shortform_name=console_name.lower()[:4],
                device_game_folder=game_folder,
                device_save_folder=save_folder,
                device_state_folder=state_folder,
                device_emulator=emulator,
            )
            store.set_console(console_obj)

    click.echo(f"Added: {name} (slug: {actual_slug})")


@game.command("list")
def game_list() -> None:
    """List all managed games with device installations."""
    client = _client()
    games = client.list_games()
    if not games:
        click.echo("No games added yet. Use 'emusync game add' to add one.")
        return

    rows = []
    for g in games:
        devices = client.list_game_devices(g['slug'])
        if not devices:
            rows.append([g['name'], "-", "-", "-", "-"])
        else:
            # Find default save folder structure across all devices
            default_save_dir = None
            for d in devices:
                save_path = d.get('save_path', '-')
                if save_path and save_path != '-':
                    default_save_dir = os.path.dirname(save_path)
                    break

            for i, device in enumerate(devices):
                name = g['name'] if i == 0 else ""
                state_path = device.get('state_path', '-')
                save_path = device.get('save_path', '-')
                rom_path = device.get('rom_path', '-')

                # Construct and create state folder as: {parent_dir}/{game_name}/
                state_folder = '-'
                parent_dir = None
                if state_path and state_path != '-':
                    # Use configured state_path
                    parent_dir = os.path.dirname(state_path)
                elif save_path and save_path != '-':
                    # Infer from save_path by replacing 'saves' with 'states'
                    save_dir = os.path.dirname(save_path)
                    # Replace all occurrences of 'saves' with 'states' to handle nested structures
                    parent_dir = save_dir.replace('/saves/', '/states/').replace('/saves', '/states')
                    # Handle case where path starts with 'saves/'
                    if parent_dir.startswith('saves/'):
                        parent_dir = parent_dir.replace('saves/', 'states/', 1)
                elif default_save_dir:
                    # Use the default console saves folder structure and swap saves->states
                    parent_dir = default_save_dir.replace('/saves/', '/states/').replace('/saves', '/states')
                    if parent_dir.startswith('saves/'):
                        parent_dir = parent_dir.replace('saves/', 'states/', 1)

                if parent_dir and parent_dir != '-':
                    state_folder_path = os.path.join(parent_dir, g['name'])
                    try:
                        os.makedirs(state_folder_path, exist_ok=True)
                        state_folder = state_folder_path + os.sep
                    except (OSError, Exception) as e:
                        # If creation fails, still show the intended path for the user to see
                        state_folder = state_folder_path + os.sep

                rows.append([
                    name,
                    device.get('name', device.get('id', '-')),
                    rom_path,
                    save_path,
                    state_folder,
                ])

    if not rows:
        click.echo("No games added yet. Use 'emusync game add' to add one.")
        return

    headers = ["Game Name", "Device", "ROM Path", "Save Path", "State Folder"]
    col_widths = [max(len(headers[i]), max(len(str(row[i])) for row in rows)) for i in range(5)]

    header_line = "  ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    separator = "  ".join("-" * w for w in col_widths)

    click.echo(header_line)
    click.echo(separator)
    for row in rows:
        click.echo("  ".join(str(row[i]).ljust(col_widths[i]) for i in range(5)))


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


# ── console ───────────────────────────────────────────────────────────────────

@cli.group()
def console() -> None:
    """Manage console/emulator configurations."""


@console.command("list")
def console_list() -> None:
    """List all configured consoles with device installations."""
    from server.store import Store
    cfg = cfg_module.load()
    store = Store(cfg.data_dir)

    devices = store.list_devices()
    if not devices:
        click.echo("No devices configured.")
        return

    rows = []
    for device in devices:
        consoles = store.list_consoles(device.id)
        if not consoles:
            continue
        for console in consoles:
            rows.append([
                console.console_name,
                device.name,
                console.device_emulator or '-',
                console.device_game_folder or '-',
                console.device_save_folder or '-',
                console.device_state_folder or '-',
            ])

    if not rows:
        click.echo("No consoles configured.")
        return

    headers = ["Console", "Device", "Emulator/Core", "ROM Path", "Save Path", "State Path"]
    col_widths = [max(len(headers[i]), max(len(str(row[i])) for row in rows)) for i in range(6)]

    header_line = "  ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    separator = "  ".join("-" * w for w in col_widths)

    click.echo(header_line)
    click.echo(separator)
    for row in rows:
        click.echo("  ".join(str(row[i]).ljust(col_widths[i]) for i in range(6)))


# ── Console import helpers ────────────────────────────────────────────────────

_IMPORT_CONSOLES = [
    {"key": "gba",     "label": "Game Boy Advance",          "abbr": "GBA",
     "system_keys": ["gba"],
     "standalones": [{"id": "mgba", "label": "mGBA",
                      "native_bins": ["/usr/bin/mgba-qt", "/usr/bin/mgba",
                                      str(Path.home() / ".local/bin/mgba-qt")],
                      "flatpak_id": "io.mgba.mGBA",
                      "flatpak_exec": "flatpak run io.mgba.mGBA",
                      "save_dir": str(Path.home() / ".local/share/mGBA/saves")}],
     "suggestions": ["RetroArch with mGBA core", "mGBA standalone"]},
    {"key": "gb",      "label": "Game Boy / Game Boy Color", "abbr": "GB",
     "system_keys": ["gb", "gbc"],
     "standalones": [{"id": "mgba", "label": "mGBA",
                      "native_bins": ["/usr/bin/mgba-qt", "/usr/bin/mgba"],
                      "flatpak_id": "io.mgba.mGBA",
                      "flatpak_exec": "flatpak run io.mgba.mGBA",
                      "save_dir": str(Path.home() / ".local/share/mGBA/saves")}],
     "suggestions": ["RetroArch with Gambatte or mGBA core", "mGBA standalone"]},
    {"key": "snes",    "label": "Super Nintendo (SNES)",      "abbr": "SNES",
     "system_keys": ["sfc", "smc"],
     "standalones": [], "suggestions": ["RetroArch with Snes9x core"]},
    {"key": "nes",     "label": "NES / Famicom",              "abbr": "NES",
     "system_keys": ["nes", "fds"],
     "standalones": [], "suggestions": ["RetroArch with Nestopia UE or FCEUmm core"]},
    {"key": "n64",     "label": "Nintendo 64",                "abbr": "N64",
     "system_keys": ["n64", "z64", "v64"],
     "standalones": [], "suggestions": ["RetroArch with Mupen64Plus-Next core"]},
    {"key": "nds",     "label": "Nintendo DS",                "abbr": "NDS",
     "system_keys": ["nds"],
     "standalones": [], "suggestions": ["RetroArch with melonDS or DeSmuME core"]},
    {"key": "genesis", "label": "Sega Genesis / Mega Drive",  "abbr": "Genesis",
     "system_keys": ["md", "smd", "gen"],
     "standalones": [], "suggestions": ["RetroArch with Genesis Plus GX core"]},
    {"key": "sms",     "label": "Master System / Game Gear",  "abbr": "SMS",
     "system_keys": ["sms", "gg"],
     "standalones": [], "suggestions": ["RetroArch with Genesis Plus GX core"]},
    {"key": "pce",     "label": "PC Engine",                  "abbr": "PCE",
     "system_keys": ["pce"],
     "standalones": [], "suggestions": ["RetroArch with Beetle PCE core"]},
    {"key": "psx",     "label": "PlayStation",                "abbr": "PSX",
     "system_keys": ["iso", "bin", "cue", "chd", "pbp"],
     "standalones": [], "suggestions": ["RetroArch with PCSX-ReARMed or Beetle PSX core"]},
]

_IMPORT_SYSTEMS: dict[str, dict] = {
    "gba": {"name": "Game Boy Advance", "save_exts": ["sav", "srm"],
            "cores": [{"lib": "mgba_libretro", "folder": "mGBA"},
                      {"lib": "vba_next_libretro", "folder": "VBA Next"},
                      {"lib": "vbam_libretro", "folder": "VBA-M"}]},
    "gb":  {"name": "Game Boy", "save_exts": ["sav", "srm"],
            "cores": [{"lib": "gambatte_libretro", "folder": "Gambatte"},
                      {"lib": "mgba_libretro", "folder": "mGBA"},
                      {"lib": "gearboy_libretro", "folder": "Gearboy"}]},
    "gbc": {"name": "Game Boy Color", "save_exts": ["sav", "srm"],
            "cores": [{"lib": "gambatte_libretro", "folder": "Gambatte"},
                      {"lib": "mgba_libretro", "folder": "mGBA"},
                      {"lib": "gearboy_libretro", "folder": "Gearboy"}]},
    "sfc": {"name": "SNES", "save_exts": ["srm", "sav"],
            "cores": [{"lib": "snes9x_libretro", "folder": "Snes9x"},
                      {"lib": "bsnes_libretro", "folder": "bsnes"},
                      {"lib": "snes9x2010_libretro", "folder": "Snes9x 2010"}]},
    "smc": {"name": "SNES", "save_exts": ["srm", "sav"],
            "cores": [{"lib": "snes9x_libretro", "folder": "Snes9x"},
                      {"lib": "bsnes_libretro", "folder": "bsnes"},
                      {"lib": "snes9x2010_libretro", "folder": "Snes9x 2010"}]},
    "nes": {"name": "NES", "save_exts": ["sav", "srm"],
            "cores": [{"lib": "nestopia_libretro", "folder": "Nestopia UE"},
                      {"lib": "fceumm_libretro", "folder": "FCEUmm"},
                      {"lib": "mesen_libretro", "folder": "Mesen"}]},
    "fds": {"name": "Famicom Disk System", "save_exts": ["sav", "srm"],
            "cores": [{"lib": "nestopia_libretro", "folder": "Nestopia UE"},
                      {"lib": "fceumm_libretro", "folder": "FCEUmm"}]},
    "n64": {"name": "Nintendo 64", "save_exts": ["srm", "sav", "eep", "mpk"],
            "cores": [{"lib": "mupen64plus_next_libretro", "folder": "Mupen64Plus-Next"},
                      {"lib": "parallel_n64_libretro", "folder": "ParaLLEl N64"}]},
    "z64": {"name": "Nintendo 64", "save_exts": ["srm", "sav", "eep", "mpk"],
            "cores": [{"lib": "mupen64plus_next_libretro", "folder": "Mupen64Plus-Next"},
                      {"lib": "parallel_n64_libretro", "folder": "ParaLLEl N64"}]},
    "v64": {"name": "Nintendo 64", "save_exts": ["srm", "sav", "eep", "mpk"],
            "cores": [{"lib": "mupen64plus_next_libretro", "folder": "Mupen64Plus-Next"},
                      {"lib": "parallel_n64_libretro", "folder": "ParaLLEl N64"}]},
    "nds": {"name": "Nintendo DS", "save_exts": ["sav", "dsv", "srm"],
            "cores": [{"lib": "melonds_libretro", "folder": "melonDS"},
                      {"lib": "desmume_libretro", "folder": "DeSmuME"},
                      {"lib": "desmume2015_libretro", "folder": "DeSmuME 2015"}]},
    "md":  {"name": "Sega Genesis", "save_exts": ["srm", "sav"],
            "cores": [{"lib": "genesis_plus_gx_libretro", "folder": "Genesis Plus GX"},
                      {"lib": "picodrive_libretro", "folder": "PicoDrive"}]},
    "smd": {"name": "Sega Genesis", "save_exts": ["srm", "sav"],
            "cores": [{"lib": "genesis_plus_gx_libretro", "folder": "Genesis Plus GX"},
                      {"lib": "picodrive_libretro", "folder": "PicoDrive"}]},
    "gen": {"name": "Sega Genesis", "save_exts": ["srm", "sav"],
            "cores": [{"lib": "genesis_plus_gx_libretro", "folder": "Genesis Plus GX"},
                      {"lib": "picodrive_libretro", "folder": "PicoDrive"}]},
    "sms": {"name": "Sega Master System", "save_exts": ["srm", "sav"],
            "cores": [{"lib": "genesis_plus_gx_libretro", "folder": "Genesis Plus GX"},
                      {"lib": "picodrive_libretro", "folder": "PicoDrive"}]},
    "gg":  {"name": "Game Gear", "save_exts": ["srm", "sav"],
            "cores": [{"lib": "genesis_plus_gx_libretro", "folder": "Genesis Plus GX"}]},
    "pce": {"name": "PC Engine", "save_exts": ["srm", "sav"],
            "cores": [{"lib": "mednafen_pce_libretro", "folder": "Beetle PCE"},
                      {"lib": "mednafen_pce_fast_libretro", "folder": "Beetle PCE Fast"}]},
    "iso": {"name": "Disc", "save_exts": ["mcr", "srm", "sav"],
            "cores": [{"lib": "pcsx_rearmed_libretro", "folder": "PCSX-ReARMed"},
                      {"lib": "mednafen_psx_libretro", "folder": "Beetle PSX"},
                      {"lib": "flycast_libretro", "folder": "Flycast"}]},
    "bin": {"name": "Disc", "save_exts": ["mcr", "srm", "sav"],
            "cores": [{"lib": "pcsx_rearmed_libretro", "folder": "PCSX-ReARMed"},
                      {"lib": "mednafen_psx_libretro", "folder": "Beetle PSX"}]},
    "cue": {"name": "Disc", "save_exts": ["mcr", "srm", "sav"],
            "cores": [{"lib": "pcsx_rearmed_libretro", "folder": "PCSX-ReARMed"},
                      {"lib": "mednafen_psx_libretro", "folder": "Beetle PSX"}]},
    "chd": {"name": "Disc (CHD)", "save_exts": ["mcr", "srm", "sav"],
            "cores": [{"lib": "pcsx_rearmed_libretro", "folder": "PCSX-ReARMed"},
                      {"lib": "mednafen_psx_libretro", "folder": "Beetle PSX"},
                      {"lib": "flycast_libretro", "folder": "Flycast"}]},
    "pbp": {"name": "PSP / PS1", "save_exts": ["srm", "sav", "mcr"],
            "cores": [{"lib": "ppsspp_libretro", "folder": "PPSSPP"},
                      {"lib": "pcsx_rearmed_libretro", "folder": "PCSX-ReARMed"}]},
}

_DEFAULT_SAVE_EXTS = ["srm", "sav", "save"]
_DEFAULT_STATE_EXTS = ["state", "state.auto"]


def _parse_retroarch_cfg(cfg_path: str) -> dict[str, str]:
    """Parse key = "value" lines from a retroarch.cfg, expanding leading ~/."""
    out: dict[str, str] = {}
    if not os.path.exists(cfg_path):
        return out
    home = str(Path.home())
    with open(cfg_path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = re.match(r'^\s*(\w+)\s*=\s*"?([^"#\r\n]*)"?\s*$', line)
            if m:
                key, val = m.group(1).strip(), m.group(2).strip()
                if val.startswith("~/"):
                    val = os.path.join(home, val[2:])
                elif val == "~":
                    val = home
                out[key] = val
    return out


def _detect_retroarch() -> list[dict]:
    """Return list of detected RetroArch installs (native + flatpak)."""
    home = str(Path.home())
    infos: list[dict] = []

    # Native
    native_bins = ["/usr/bin/retroarch", "/usr/local/bin/retroarch",
                   os.path.join(home, ".local/bin/retroarch")]
    native_cfg = os.path.join(home, ".config/retroarch/retroarch.cfg")
    for bin_path in native_bins:
        if os.path.exists(bin_path):
            cfg = _parse_retroarch_cfg(native_cfg)
            rom_dir = cfg.get("rgui_browser_directory", "")
            if rom_dir == "default":
                rom_dir = ""
            infos.append({
                "type": "native",
                "label": "RetroArch",
                "exec_path": bin_path,
                "save_dir": cfg.get("savefile_directory") or os.path.join(home, ".config/retroarch/saves"),
                "states_dir": cfg.get("savestate_directory") or os.path.join(home, ".config/retroarch/states"),
                "cores_dir": cfg.get("libretro_directory") or os.path.join(home, ".config/retroarch/cores"),
                "rom_dirs": [rom_dir] if rom_dir else [],
            })
            break

    # Flatpak
    try:
        result = subprocess.run(
            ["flatpak", "list", "--app", "--columns=application"],
            capture_output=True, text=True, timeout=5,
        )
        if "org.libretro.RetroArch" in result.stdout:
            flat_cfg_path = os.path.join(
                home, ".var/app/org.libretro.RetroArch/config/retroarch/retroarch.cfg"
            )
            cfg = _parse_retroarch_cfg(flat_cfg_path)
            rom_dir = cfg.get("rgui_browser_directory", "")
            if rom_dir == "default":
                rom_dir = ""
            infos.append({
                "type": "flatpak",
                "label": "RetroArch (Flatpak)",
                "exec_path": "flatpak run org.libretro.RetroArch",
                "save_dir": cfg.get("savefile_directory") or os.path.join(
                    home, ".var/app/org.libretro.RetroArch/config/retroarch/saves"),
                "states_dir": cfg.get("savestate_directory") or os.path.join(
                    home, ".var/app/org.libretro.RetroArch/config/retroarch/states"),
                "cores_dir": cfg.get("libretro_directory") or os.path.join(
                    home, ".var/app/org.libretro.RetroArch/data/retroarch/cores"),
                "rom_dirs": [rom_dir] if rom_dir else [],
            })
    except Exception:
        pass

    return infos


def _find_installed_core(cores_dir: str, system: dict) -> dict | None:
    """Return first core whose .so exists in cores_dir, or None."""
    for core in system["cores"]:
        so_path = os.path.join(cores_dir, f"{core['lib']}.so")
        if os.path.exists(so_path):
            return {"lib": so_path, "folder": core["folder"]}
    return None


def _detect_emulators_for_console(console_def: dict) -> list[dict]:
    """Detect installed emulators/cores for a console. Mirrors detectEmulatorsForConsole in main.ts."""
    home = str(Path.home())
    options: list[dict] = []

    # RetroArch
    seen_cores: set[str] = set()
    for ra in _detect_retroarch():
        for sys_key in console_def["system_keys"]:
            system = _IMPORT_SYSTEMS.get(sys_key)
            if not system:
                continue
            core = _find_installed_core(ra["cores_dir"], system)
            if not core or core["lib"] in seen_cores:
                continue
            seen_cores.add(core["lib"])
            save_dir = os.path.join(ra["save_dir"], core["folder"])
            state_dir = os.path.join(ra["states_dir"], core["folder"])
            options.append({
                "id": f"{ra['type']}-{core['folder'].lower().replace(' ', '-')}",
                "label": f"{ra['label']} · {core['folder']}",
                "exec_path": ra["exec_path"],
                "save_dir": save_dir,
                "state_dir": state_dir,
                "core_path": core["lib"],
                "core_folder": core["folder"],
                "rom_dirs": ra["rom_dirs"],
            })

    # Standalone emulators
    flatpak_list: str | None = None
    for s in console_def.get("standalones", []):
        found = False
        for bin_path in s["native_bins"]:
            if os.path.exists(bin_path):
                options.append({
                    "id": f"{s['id']}-native",
                    "label": s["label"],
                    "exec_path": bin_path,
                    "save_dir": s["save_dir"],
                    "state_dir": None,
                    "core_path": None,
                    "core_folder": None,
                    "rom_dirs": [],
                })
                found = True
                break
        if not found and s.get("flatpak_id"):
            if flatpak_list is None:
                try:
                    r = subprocess.run(
                        ["flatpak", "list", "--app", "--columns=application"],
                        capture_output=True, text=True, timeout=5,
                    )
                    flatpak_list = r.stdout
                except Exception:
                    flatpak_list = ""
            if s["flatpak_id"] in flatpak_list:
                options.append({
                    "id": f"{s['id']}-flatpak",
                    "label": f"{s['label']} (Flatpak)",
                    "exec_path": s["flatpak_exec"],
                    "save_dir": os.path.join(
                        home, f".var/app/{s['flatpak_id']}/data/{s['id']}/saves"),
                    "state_dir": None,
                    "core_path": None,
                    "core_folder": None,
                    "rom_dirs": [],
                })

    return options


_ROM_EXTENSIONS = {
    "sfc", "smc", "gb", "gbc", "gba", "nes", "fds",
    "n64", "z64", "v64", "nds", "md", "smd", "gen",
    "sms", "gg", "pce", "iso", "cue", "bin", "chd", "pbp",
}


def _scan_rom_dir(directory: str, depth: int = 0) -> list[str]:
    """Recursively collect ROM files (depth ≤ 3)."""
    if depth > 3:
        return []
    roms: list[str] = []
    try:
        with os.scandir(directory) as it:
            for entry in it:
                if entry.is_file():
                    ext = os.path.splitext(entry.name)[1].lstrip(".").lower()
                    if ext in _ROM_EXTENSIONS:
                        roms.append(entry.path)
                elif entry.is_dir():
                    roms.extend(_scan_rom_dir(entry.path, depth + 1))
    except PermissionError:
        pass
    return roms


def _match_save_file(save_dir: str, base_name: str, exts: list[str]) -> dict:
    """Find save file in save_dir matching base_name + any extension."""
    for ext in exts:
        p = os.path.join(save_dir, f"{base_name}.{ext}")
        if os.path.exists(p):
            return {"path": p, "exists": True}
    return {"path": os.path.join(save_dir, f"{base_name}.{exts[0]}"), "exists": False}


@console.command("import")
def console_import() -> None:
    """Interactive wizard to bulk-import ROMs for a console (mirrors the GUI Add Console wizard)."""
    import httpx

    # ── Step 1: select console ────────────────────────────────────────────────
    click.echo("\nAvailable consoles:")
    for i, c in enumerate(_IMPORT_CONSOLES, 1):
        click.echo(f"  {i:>2}. {c['label']}")

    choice = click.prompt(
        "\nSelect console",
        type=click.IntRange(1, len(_IMPORT_CONSOLES)),
    )
    console_def = _IMPORT_CONSOLES[choice - 1]
    click.echo(f"\nSelected: {console_def['label']}")

    # ── Step 2: detect emulators/cores ───────────────────────────────────────
    click.echo("Looking for compatible emulators…")
    emulators = _detect_emulators_for_console(console_def)

    if not emulators:
        click.echo(f"\nNo compatible emulator found for {console_def['label']}.")
        if console_def.get("suggestions"):
            click.echo("Install one of:")
            for s in console_def["suggestions"]:
                click.echo(f"  • {s}")
        return

    if len(emulators) == 1:
        emu = emulators[0]
        click.echo(f"Found: {emu['label']}  (saves: {emu['save_dir']})")
    else:
        click.echo("\nMultiple emulators found:")
        for i, e in enumerate(emulators, 1):
            click.echo(f"  {i}. {e['label']}  (saves: {e['save_dir']})")
        emu_choice = click.prompt(
            "Select emulator",
            type=click.IntRange(1, len(emulators)),
        )
        emu = emulators[emu_choice - 1]

    # ── Step 3: ROM folder ────────────────────────────────────────────────────
    suggested_dirs = emu.get("rom_dirs", [])
    if suggested_dirs:
        click.echo(f"\nRetroArch ROM directory: {suggested_dirs[0]}")

    rom_folder = click.prompt(
        "\nPath to ROM folder",
        default=suggested_dirs[0] if suggested_dirs else "",
    ).strip()

    if not rom_folder or not os.path.isdir(rom_folder):
        click.echo("Error: folder not found.")
        return

    # ── Step 4: scan for ROMs ─────────────────────────────────────────────────
    click.echo("Scanning for ROMs and saves…")

    rom_ext_set = set(console_def["system_keys"])
    all_files = _scan_rom_dir(rom_folder)
    matching = [p for p in all_files
                if os.path.splitext(p)[1].lstrip(".").lower() in rom_ext_set]

    if not matching:
        click.echo("No ROMs found in that folder.")
        return

    # Build ROM entries (same logic as main.ts emulator:scan handler)
    first_sys_key = console_def["system_keys"][0]
    default_save_exts = _IMPORT_SYSTEMS.get(first_sys_key, {}).get("save_exts", _DEFAULT_SAVE_EXTS)

    entries: list[dict] = []
    for rom_path in sorted(matching):
        ext = os.path.splitext(rom_path)[1].lstrip(".").lower()
        system = _IMPORT_SYSTEMS.get(ext, {})
        save_exts = system.get("save_exts", default_save_exts)
        base = os.path.splitext(os.path.basename(rom_path))[0]

        save_match = _match_save_file(emu["save_dir"], base, save_exts)
        # Fallback: check root saves dir for pre-core-organisation saves
        if not save_match["exists"] and emu.get("core_folder"):
            root_save_dir = os.path.dirname(emu["save_dir"])
            root_match = _match_save_file(root_save_dir, base, save_exts)
            if root_match["exists"]:
                save_match = root_match

        state_match: dict | None = None
        if emu.get("state_dir"):
            state_match = _match_save_file(emu["state_dir"], base, _DEFAULT_STATE_EXTS)
            if not state_match["exists"] and emu.get("core_folder"):
                root_state_dir = os.path.dirname(emu["state_dir"])
                root_sm = _match_save_file(root_state_dir, base, _DEFAULT_STATE_EXTS)
                if root_sm["exists"]:
                    state_match = root_sm

        if emu.get("core_path"):
            launch_cmd = f'{emu["exec_path"]} -L "{emu["core_path"]}" "{rom_path}"'
        else:
            launch_cmd = f'{emu["exec_path"]} "{rom_path}"'

        entries.append({
            "name": base,
            "rom_path": rom_path,
            "save_path": save_match["path"],
            "save_exists": save_match["exists"],
            "state_path": state_match["path"] if state_match and state_match["exists"] else "",
            "launch_command": launch_cmd,
            "rom_folder_path": rom_folder,
        })

    # Dedup: filter out ROMs already imported on this device
    try:
        client = _client()
        existing_games = client.list_games()
        imported_roms: set[str] = set()
        for g in existing_games:
            try:
                gd = client.get_game_device(g["slug"])
                if gd and gd.rom_path:
                    imported_roms.add(gd.rom_path)
                    imported_roms.add(os.path.splitext(os.path.basename(gd.rom_path))[0].lower())
            except Exception:
                pass
        before = len(entries)
        entries = [e for e in entries
                   if e["rom_path"] not in imported_roms
                   and os.path.splitext(os.path.basename(e["rom_path"]))[0].lower() not in imported_roms]
        skipped = before - len(entries)
        if skipped:
            click.echo(f"Skipped {skipped} already-imported ROM(s).")
    except Exception:
        pass

    if not entries:
        click.echo("All ROMs found are already imported on this device.")
        return

    # ── Step 5: show ROMs, let user deselect ──────────────────────────────────
    click.echo(f"\nFound {len(entries)} ROM(s):\n")
    for i, e in enumerate(entries, 1):
        save_tag = "  [save found]" if e["save_exists"] else ""
        state_tag = "  [state found]" if e["state_path"] else ""
        click.echo(f"  {i:>3}. {e['name']}{save_tag}{state_tag}")

    click.echo(
        "\nEnter numbers to exclude (comma-separated), or press Enter to import all:"
    )
    exclude_input = input().strip()
    exclude_indices: set[int] = set()
    if exclude_input:
        for part in exclude_input.split(","):
            part = part.strip()
            if part.isdigit():
                idx = int(part)
                if 1 <= idx <= len(entries):
                    exclude_indices.add(idx)

    to_import = [e for i, e in enumerate(entries, 1) if i not in exclude_indices]

    if not to_import:
        click.echo("Nothing selected. Exiting.")
        return

    if not click.confirm(f"\nImport {len(to_import)} game(s) for {console_def['label']}?"):
        return

    # ── Step 6: import ────────────────────────────────────────────────────────
    client = _client()
    console_abbr = console_def["abbr"]
    errors: list[str] = []

    for i, entry in enumerate(to_import, 1):
        click.echo(f"  [{i}/{len(to_import)}] {entry['name']}… ", nl=False)
        try:
            game = client.add_game(entry["name"], console_abbr)
            slug = game["slug"]
            client.set_game_device(slug, GameDeviceConfig(
                rom_path=entry["rom_path"],
                save_path=entry["save_path"],
                launch_command=entry["launch_command"],
                state_path=entry["state_path"],
                rom_folder_path=entry["rom_folder_path"],
            ))
            click.echo("ok")
        except (httpx.HTTPStatusError, httpx.RequestError, Exception) as exc:
            click.echo(f"error ({exc})")
            errors.append(entry["name"])

    click.echo(f"\nDone. {len(to_import) - len(errors)}/{len(to_import)} imported.")
    if errors:
        click.echo(f"Failed: {', '.join(errors)}")


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


# ── push ──────────────────────────────────────────────────────────────────────

def _parse_selection(raw: str, max_idx: int) -> list[int]:
    """Parse '1,3' or '1-3' or '2' into sorted 0-based indices."""
    indices: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if "-" in part:
            try:
                lo, hi = part.split("-", 1)
                for i in range(int(lo), int(hi) + 1):
                    if 1 <= i <= max_idx:
                        indices.add(i - 1)
            except ValueError:
                pass
        else:
            try:
                i = int(part)
                if 1 <= i <= max_idx:
                    indices.add(i - 1)
            except ValueError:
                pass
    return sorted(indices)


def _find_target_rom_folder(
    client: "SyncClient", slug: str, console: str, target_id: str
) -> str | None:
    """Return the ROM folder the target device uses for this console, if known."""
    # Check if target already has this specific game configured
    try:
        game_devices = client.list_game_devices(slug)
        for gd in game_devices:
            if gd["id"] == target_id and gd.get("rom_folder_path"):
                return gd["rom_folder_path"]
    except Exception:
        pass

    # Fall back to the target device's console config
    if console:
        try:
            consoles = client.get_device_consoles(target_id)
            for c in consoles:
                if c["console_name"] == console and c.get("device_game_folder"):
                    return c["device_game_folder"]
        except Exception:
            pass

    return None


@cli.command("push")
def push_rom() -> None:
    """Push a ROM file to another device via the server."""
    cfg = cfg_module.load()
    if not cfg.server_host:
        click.echo("EmuSync is not configured. Run 'emusync device connect' first.", err=True)
        sys.exit(1)

    client = _client(cfg)

    if not client.health():
        click.echo("Cannot reach EmuSync server. Is it running?", err=True)
        sys.exit(1)

    # Step 1: list games this device has with a ROM configured
    try:
        my_games = client.list_my_game_devices()
    except Exception as e:
        click.echo(f"Failed to fetch games: {e}", err=True)
        sys.exit(1)

    pushable = [g for g in my_games if g.get("rom_path")]
    if not pushable:
        click.echo("No games with a ROM path configured on this device.")
        return

    click.echo("\nGames available to push:")
    for i, g in enumerate(pushable, 1):
        rom_name = os.path.basename(g["rom_path"])
        console_str = f" ({g['console']})" if g.get("console") else ""
        click.echo(f"  {i:>3}. {g['name']}{console_str}  —  {rom_name}")

    raw = click.prompt("\nSelect games to push (e.g. 1  or  1,3  or  1-4)")
    selected = _parse_selection(raw, len(pushable))
    if not selected:
        click.echo("No valid selection.", err=True)
        sys.exit(1)
    selected_games = [pushable[i] for i in selected]

    # Step 2: list other devices
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
    target_is_online = target.get("is_online", False)

    # Step 3: for each selected game, confirm destination and upload
    for game in selected_games:
        slug = game["slug"]
        rom_path = game["rom_path"]
        console = game.get("console", "")
        game_name = game["name"]
        rom_filename = os.path.basename(rom_path)

        click.echo(f"\n── {game_name} ──")

        if not os.path.isfile(rom_path):
            click.echo(f"  ROM file not found: {rom_path}", err=True)
            continue

        # Find suggested destination on target
        suggested_folder = _find_target_rom_folder(client, slug, console, target["id"])
        if suggested_folder:
            console_label = console if console else "ROM folder"
            if click.confirm(
                f"  {console_label} found on {target['name']} — place '{rom_filename}' in {suggested_folder}?",
                default=True,
            ):
                destination_path = os.path.join(suggested_folder, rom_filename)
            else:
                destination_path = click.prompt("  Where should the ROM be installed on the device?")
        else:
            label = console if console else "Console"
            click.echo(f"  {label} not yet set up on {target['name']}.")
            destination_path = click.prompt("  Where should the ROM be installed on the device?")

        # Upload
        file_mb = os.path.getsize(rom_path) / (1024 * 1024)
        click.echo(f"  Uploading {rom_filename} ({file_mb:.1f} MB)...")
        try:
            result = client.create_rom_transfer(slug, target["id"], destination_path, rom_path)
        except Exception as e:
            click.echo(f"  Failed: {e}", err=True)
            continue

        if result.get("target_online"):
            click.echo(f"  Queued — {target['name']} is online and will receive it shortly.")
        else:
            click.echo(f"  Warning: {target['name']} is offline — transfer will be delivered when it comes online.")


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
