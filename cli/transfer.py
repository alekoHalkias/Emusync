"""ROM transfer commands (`push`, `pull`) and the `sync-daemon` that fulfills
transfers automatically over SSE."""
from __future__ import annotations

import os
import sys

import click

import server.config as cfg_module
from server.sync_client import GameDeviceConfig, SyncClient

from cli import netrom
from cli.common import _client
from cli.root import cli


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


def _find_local_rom_folder(client: "SyncClient", console: str) -> str | None:
    """Return the local ROM folder this device uses for a given console, if known."""
    if not console:
        return None
    try:
        my_games = client.list_my_game_devices()
        for g in my_games:
            if g.get("console") == console and g.get("rom_folder_path"):
                return g["rom_folder_path"]
    except Exception:
        pass
    return None


@cli.command("pull")
def pull_rom() -> None:
    """Pull a ROM file from another device to this one via the server."""
    cfg = cfg_module.load()
    if not cfg.server_host and not cfg.is_server:
        click.echo("EmuSync is not configured. Run 'emusync device connect' first.", err=True)
        sys.exit(1)

    client = _client(cfg)

    if not client.health():
        click.echo("Cannot reach EmuSync server. Is it running?", err=True)
        sys.exit(1)

    # Step 1: list other paired devices
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

    source_idx = click.prompt("Select source device", type=int) - 1
    if not (0 <= source_idx < len(others)):
        click.echo("Invalid selection.", err=True)
        sys.exit(1)

    source = others[source_idx]

    # Step 2: list games on source device that have a ROM configured
    try:
        source_games = client.list_device_games(source["id"])
    except Exception as e:
        click.echo(f"Failed to fetch games from {source['name']}: {e}", err=True)
        sys.exit(1)

    pullable = [g for g in source_games if g.get("rom_path")]
    if not pullable:
        click.echo(f"{source['name']} has no games with a ROM path configured.")
        return

    click.echo(f"\nGames available to pull from {source['name']}:")
    for i, g in enumerate(pullable, 1):
        rom_name = os.path.basename(g["rom_path"])
        console_str = f" ({g['console']})" if g.get("console") else ""
        click.echo(f"  {i:>3}. {g['name']}{console_str}  —  {rom_name}")

    raw = click.prompt("\nSelect games to pull (e.g. 1  or  1,3  or  1-4)")
    selected = _parse_selection(raw, len(pullable))
    if not selected:
        click.echo("No valid selection.", err=True)
        sys.exit(1)
    selected_games = [pullable[i] for i in selected]

    # Step 3: for each game, confirm local destination and send pull request
    for game in selected_games:
        slug = game["slug"]
        console = game.get("console", "")
        game_name = game["name"]
        rom_filename = os.path.basename(game["rom_path"])

        click.echo(f"\n── {game_name} ──")

        # Find suggested local destination
        suggested_folder = _find_local_rom_folder(client, console)
        if suggested_folder:
            console_label = console if console else "ROM folder"
            if click.confirm(
                f"  {console_label} found locally — place '{rom_filename}' in {suggested_folder}?",
                default=True,
            ):
                dest_folder = suggested_folder
            else:
                dest_folder = click.prompt("  Which local folder should the ROM go in?")
        else:
            label = console if console else "Console"
            click.echo(f"  {label} not yet set up on this device.")
            dest_folder = click.prompt("  Which local folder should the ROM go in?")

        destination_path = os.path.join(dest_folder.rstrip("/\\"), rom_filename)

        # Send pull request to server
        click.echo(f"  Requesting '{rom_filename}' from {source['name']}...")
        try:
            result = client.create_pull_request(slug, source["id"], destination_path)
        except Exception as e:
            click.echo(f"  Failed: {e}", err=True)
            continue

        if result.get("source_online"):
            click.echo(f"  {game_name} pulled from {source['name']} and will be available on this device shortly.")
        else:
            click.echo(f"  Warning: {source['name']} is offline — {game_name} will be sent when it comes online.")


@cli.command("push")
def push_rom() -> None:
    """Push a ROM file to another device via the server."""
    cfg = cfg_module.load()
    if not cfg.server_host and not cfg.is_server:
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

    # Step 3: for each selected game, confirm destination and upload
    for game in selected_games:
        slug = game["slug"]
        rom_path = game["rom_path"]
        console = game.get("console", "")
        game_name = game["name"]
        rom_filename = os.path.basename(rom_path)

        click.echo(f"\n── {game_name} ──")

        if not netrom.path_is_reachable(rom_path):
            click.echo(f"  ROM file not reachable: {rom_path}", err=True)
            continue

        # Find suggested destination on target
        suggested_folder = _find_target_rom_folder(client, slug, console, target["id"])
        if suggested_folder:
            console_label = console if console else "ROM folder"
            if click.confirm(
                f"  {console_label} found on {target['name']} — place '{rom_filename}' in {suggested_folder}?",
                default=True,
            ):
                dest_folder = suggested_folder
            else:
                dest_folder = click.prompt("  Which folder should the ROM go in?")
        else:
            label = console if console else "Console"
            click.echo(f"  {label} not yet set up on {target['name']}.")
            dest_folder = click.prompt("  Which folder should the ROM go in?")

        destination_path = os.path.join(dest_folder.rstrip("/\\"), rom_filename)

        # Upload
        file_mb = os.path.getsize(rom_path) / (1024 * 1024)
        click.echo(f"  Uploading {rom_filename} ({file_mb:.1f} MB)...")
        try:
            result = client.create_rom_transfer(slug, target["id"], destination_path, rom_path)
        except Exception as e:
            click.echo(f"  Failed: {e}", err=True)
            continue

        if result.get("target_online"):
            click.echo(f"  {game_name} pushed to {target['name']} and will be available on it shortly.")
        else:
            click.echo(f"  Warning: {target['name']} is offline — {game_name} will be delivered when it comes online.")


def _receive_transfer(
    client: "SyncClient",
    transfer_id: str,
    destination_path: str,
    slug: str,
    console: str,
    game_name: str,
    log=click.echo,
    sha256: str | None = None,
) -> bool:
    """Download one pending transfer, save it, register the game. Returns True on success."""
    try:
        log(f"  Receiving {game_name}...")
        client.download_transfer(transfer_id, destination_path, expected_hash=sha256)
        client.complete_transfer(transfer_id)
        log(f"  Saved to {destination_path}")
    except Exception as e:
        log(f"  Failed to receive {game_name}: {e}")
        try:
            client.complete_transfer(transfer_id, status="failed")
        except Exception:
            pass
        return False

    # Organise ROM into a per-game subfolder if it sits directly in the
    # destination folder.  Convention: roms/GameName/GameName.gba
    scan_root = os.path.dirname(destination_path)
    rom_stem = os.path.splitext(os.path.basename(destination_path))[0]
    if os.path.basename(scan_root) != rom_stem:
        subfolder = os.path.join(scan_root, rom_stem)
        os.makedirs(subfolder, exist_ok=True)
        new_path = os.path.join(subfolder, os.path.basename(destination_path))
        os.rename(destination_path, new_path)
        destination_path = new_path
        log(f"  Organised into {subfolder}/")

    # Auto-register the game on this device
    try:
        save_path = ""
        launch_command = ""
        state_path = ""

        # Copy save/launch/state patterns from another game of the same console on this device
        if console:
            my_games = client.list_my_game_devices()
            ref = next(
                (g for g in my_games if g.get("console") == console and g.get("rom_path") and g["slug"] != slug),
                None,
            )
            if ref and ref.get("save_path"):
                old_stem = os.path.splitext(os.path.basename(ref["rom_path"]))[0]
                new_stem = os.path.splitext(os.path.basename(destination_path))[0]
                save_path = ref["save_path"].replace(old_stem, new_stem)
                if ref.get("launch_command"):
                    launch_command = ref["launch_command"].replace(ref["rom_path"], destination_path)
                if ref.get("state_path"):
                    state_path = ref["state_path"].replace(old_stem, new_stem)

        client.set_game_device(slug, GameDeviceConfig(
            rom_path=destination_path,
            save_path=save_path,
            launch_command=launch_command,
            state_path=state_path,
            rom_folder_path=scan_root,
        ))
        log(f"  Registered '{game_name}' in game list")
    except Exception as e:
        log(f"  Warning: could not register game: {e}")

    return True


def _handle_pull_request(
    client: "SyncClient",
    pull_request_id: str,
    slug: str,
    to_device_id: str,
    destination_path: str,
    game_name: str,
    log=click.echo,
) -> bool:
    """Fulfill a pull request: upload local ROM to server staging for the requester."""
    try:
        my_games = client.list_my_game_devices()
        game_cfg = next((g for g in my_games if g["slug"] == slug and g.get("rom_path")), None)
        if not game_cfg:
            log(f"  Cannot fulfill pull for '{game_name}': no ROM configured on this device")
            client.complete_pull_request(pull_request_id, status="failed")
            return False

        rom_path = game_cfg["rom_path"]
        # path_is_reachable (not os.path.isfile) so a hung NAS mount can't freeze
        # the sync-daemon thread fulfilling this pull request (issue #255).
        if not netrom.path_is_reachable(rom_path):
            log(f"  Cannot fulfill pull for '{game_name}': ROM file not reachable at {rom_path}")
            client.complete_pull_request(pull_request_id, status="failed")
            return False

        log(f"  Fulfilling pull request for '{game_name}'...")
        client.create_rom_transfer(slug, to_device_id, destination_path, rom_path)
        client.complete_pull_request(pull_request_id, status="fulfilled")
        log(f"  Sent '{game_name}' to requesting device")
        return True
    except Exception as e:
        log(f"  Failed to fulfill pull for '{game_name}': {e}")
        try:
            client.complete_pull_request(pull_request_id, status="failed")
        except Exception:
            pass
        return False


def _run_transfer_daemon(client: "SyncClient", device_name: str, log=click.echo,
                         shutdown_event=None, watch_cfg=None) -> None:
    """Core daemon loop: drain pending transfers/pull-requests then hold SSE connection open.

    If `watch_cfg` is a config with `watch_saves=True`, a background save/state
    watcher thread is started alongside the transfer loop (issue #242).
    """
    import threading
    import time

    def _stopping() -> bool:
        return shutdown_event is not None and shutdown_event.is_set()

    if watch_cfg is not None and getattr(watch_cfg, "watch_saves", False):
        from cli.watch import run_save_watcher
        threading.Thread(
            target=run_save_watcher,
            args=(client, watch_cfg),
            kwargs={"log": log, "shutdown_event": shutdown_event},
            daemon=True,
        ).start()

    # Drain any pending incoming transfers
    try:
        pending = client.list_pending_transfers()
        if pending:
            log(f"Picking up {len(pending)} queued transfer(s)...")
            for t in pending:
                if _stopping():
                    return
                _receive_transfer(client, t["id"], t["destination_path"],
                                  t["slug"], t.get("console", ""), t.get("game_name", t["slug"]), log,
                                  sha256=t.get("sha256"))
    except Exception as e:
        log(f"Warning: could not check pending transfers: {e}")

    # Drain any pending pull requests this device needs to fulfill
    try:
        pull_requests = client.list_pending_pull_requests()
        if pull_requests:
            log(f"Fulfilling {len(pull_requests)} queued pull request(s)...")
            for pr in pull_requests:
                if _stopping():
                    return
                _handle_pull_request(client, pr["id"], pr["slug"], pr["to_device_id"],
                                     pr["destination_path"], pr.get("game_name", pr["slug"]), log)
    except Exception as e:
        log(f"Warning: could not check pending pull requests: {e}")

    log(f"Listening for ROM transfers on {device_name}...")

    while not _stopping():
        try:
            for event in client.stream_events():
                if _stopping():
                    return
                if event.get("type") == "rom_transfer_queued":
                    _receive_transfer(
                        client,
                        event["transfer_id"],
                        event["destination_path"],
                        event.get("slug", ""),
                        event.get("console", ""),
                        event.get("game_name", event.get("slug", event["transfer_id"])),
                        log,
                        sha256=event.get("sha256"),
                    )
                elif event.get("type") == "rom_pull_requested":
                    _handle_pull_request(
                        client,
                        event["pull_request_id"],
                        event.get("slug", ""),
                        event.get("to_device_id", ""),
                        event.get("destination_path", ""),
                        event.get("game_name", event.get("slug", event["pull_request_id"])),
                        log,
                    )
        except KeyboardInterrupt:
            raise
        except Exception as e:
            if _stopping():
                return
            log(f"Connection lost ({e}). Reconnecting in 5s...")
            time.sleep(5)


@cli.command("sync-daemon")
def sync_daemon() -> None:
    """Listen for incoming ROM transfers and receive them automatically."""
    cfg = cfg_module.load()
    if not cfg.server_host and not cfg.is_server:
        click.echo("EmuSync is not configured. Run 'emusync device connect' first.", err=True)
        sys.exit(1)

    client = _client(cfg)
    if not client.health():
        click.echo("Cannot reach EmuSync server. Is it running?", err=True)
        sys.exit(1)

    try:
        _run_transfer_daemon(client, cfg.device_name, watch_cfg=cfg)
    except KeyboardInterrupt:
        click.echo("\nStopped.")
