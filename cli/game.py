"""`game` command group — add/list/edit/remove managed games."""
from __future__ import annotations

import os
import sys

import click

import server.config as cfg_module
from server.sync_client import GameDeviceConfig

from cli.common import _client, _print_table
from cli.root import cli


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
    from server.store import Store, upsert_console_for_game

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

    if console_name and (rom_path or save_path):
        upsert_console_for_game(store, cfg.device_id, console_name, rom_path, save_path, "")

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
                    state_folder = os.path.join(parent_dir, g['name']) + os.sep

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
    _print_table(headers, rows)


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
