"""`device` command group — pairing and cross-device game coverage."""
from __future__ import annotations

import sys

import click

import server.config as cfg_module
from server.mdns import discover as mdns_discover
from server.sync_client import SyncClient

from cli.common import _client
from cli.root import cli


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
