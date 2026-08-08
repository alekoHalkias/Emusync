"""`game` command group — add/list/edit/remove managed games."""
from __future__ import annotations

import os
import sys

import click

from server.store import saves_path_to_states
from server.sync_client import GameDeviceConfig

from cli.common import _client, _print_table
from cli.mod import _title_id_for
from cli.root import cli
from cli.run_switch import _find_local_switch_save, _seed_switch_save, _switch_profile_dirs


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
    client = _client()

    # Everything goes through the server API. Registering the game *with* its
    # console means the server's set_game_device auto-configures the Console row
    # (api.upsert_console_for_game) — so the CLI must not touch a local Store,
    # which on a client device is a different database than the server's.
    result = client.add_game(name, console_name)
    actual_slug = result["slug"]
    if slug and slug != actual_slug:
        click.echo(
            f"Note: the server assigned slug '{actual_slug}' (custom slugs aren't supported).",
            err=True,
        )

    if rom_path or save_path or launch_command:
        client.set_game_device(
            actual_slug,
            GameDeviceConfig(rom_path=rom_path, save_path=save_path, launch_command=launch_command),
        )

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

                # Construct state folder as: {parent_dir}/{game_name}/, inferring
                # parent_dir from the state_path, else the save dir (saves→states).
                state_folder = '-'
                parent_dir = None
                if state_path and state_path != '-':
                    parent_dir = os.path.dirname(state_path)
                elif save_path and save_path != '-':
                    parent_dir = saves_path_to_states(os.path.dirname(save_path))
                elif default_save_dir:
                    parent_dir = saves_path_to_states(default_save_dir)

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
@click.option(
    "--everywhere", is_flag=True, default=False,
    help="Fully purge the game — every paired device's config plus save/state "
         "history — instead of just unlinking it from this device.",
)
def game_remove(slug: str, everywhere: bool) -> None:
    """Remove a game from EmuSync management (does not delete files).

    By default this only unlinks the game from this device — other paired
    devices, and the game's save/state history, are untouched. Pass
    --everywhere to fully purge the game from every device instead (issue #343).
    """
    client = _client()
    game_data = client.get_game(slug)
    if not game_data:
        click.echo(f"Game '{slug}' not found.", err=True)
        sys.exit(1)

    if everywhere:
        confirmed = click.confirm(
            f"Permanently remove {game_data['name']} from EmuSync EVERYWHERE — "
            "every paired device's config and this game's full save/state "
            "history will be deleted. Files already on disk will NOT be "
            "deleted. Continue?",
            default=False,
        )
        if not confirmed:
            click.echo("Cancelled.")
            return
        client.remove_game(slug)
        click.echo(f"Removed {slug} from every device.")
        return

    confirmed = click.confirm(
        f"Remove {game_data['name']} from EmuSync on this device only? "
        "Other paired devices and this game's save/state history will NOT be "
        "touched. Save file on disk will NOT be deleted.",
        default=False,
    )
    if not confirmed:
        click.echo("Cancelled.")
        return

    client.remove_game_device(slug)
    click.echo(f"Removed: {slug} (this device only)")


@game.command("ensure-switch-save-folder")
@click.argument("slug")
def game_ensure_switch_save_folder(slug: str) -> None:
    """Make sure SLUG has a save folder on this device, seeding real save
    data from the server if another device already has some (issue #453,
    building on #443/#448).

    The title ID must already be known (`switch_title_id` set server-side,
    e.g. via the GUI's catalog lookup). If this device already has a real
    save for the game (`_find_local_switch_save`), nothing on disk is
    touched. Else `_seed_switch_save` is tried first — same helper
    `emusync run` uses to pre-seed a first-ever session, reused here so
    pairing a new device no longer means starting blind until the game is
    actually launched. Only when the server has nothing to seed either does
    this fall back to an empty placeholder in every local profile that
    doesn't already have one, same as #448's original behavior.

    Either way, once a real save is known to exist locally, `save_path` is
    persisted via `set_game_device` — this command previously only touched
    the filesystem, so the GUI's Settings/Save-history tabs (which read
    `save_path`, not the disk) never reflected a save this found or seeded.
    Skipped for a seed spread across more than one Eden profile: which one
    the player actually uses isn't decided yet, so guessing wrong here would
    point sync at the wrong folder — post-launch adoption (#443) still
    resolves that case once the game's actually played.
    """
    client = _client()
    title_id = _title_id_for(client, slug)

    def _persist_save_path(path: str) -> None:
        gd = client.get_game_device(slug)
        if gd is None:
            return
        gd.save_path = path
        try:
            client.set_game_device(slug, gd)
        except Exception as exc:
            click.echo(f"Warning: failed to record the save location: {exc}", err=True)

    existing = _find_local_switch_save(title_id)
    if existing:
        _persist_save_path(existing)
        click.echo("Already has a real save on this device — nothing to do.")
        return

    seeded = _seed_switch_save(client, slug, title_id)
    if seeded:
        if len(seeded) == 1:
            _persist_save_path(seeded[0])
        click.echo(f"Seeded existing save into {len(seeded)} folder(s):")
        for path in seeded:
            click.echo(f"  {path}")
        return

    created = []
    for profile_dir in _switch_profile_dirs():
        dest = profile_dir / title_id
        if not dest.exists():
            dest.mkdir(parents=True, exist_ok=True)
            created.append(str(dest))
    if created:
        click.echo(f"Created {len(created)} placeholder folder(s):")
        for path in created:
            click.echo(f"  {path}")
    else:
        click.echo("Already present in every local profile (or no Eden profile exists yet).")
