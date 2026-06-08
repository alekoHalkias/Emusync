"""`console` command group — list configured consoles and the import wizard."""
from __future__ import annotations

import os

import click

from server.sync_client import GameDeviceConfig

from cli.common import _client, _print_table
from cli.consoles_data import (
    _DEFAULT_SAVE_EXTS,
    _DEFAULT_STATE_EXTS,
    _IMPORT_CONSOLES,
    _IMPORT_SYSTEMS,
)
from cli.detect import _detect_emulators_for_console, _match_save_file, _scan_rom_dir
from cli.root import cli


@cli.group()
def console() -> None:
    """Manage console/emulator configurations."""


@console.command("list")
def console_list() -> None:
    """List all configured consoles with device installations."""
    import sys

    # Route through the server API, not a local Store: on a client device the
    # local DB is not the server's, so a direct Store read would show stale data.
    client = _client()
    if not client.health():
        click.echo("Cannot reach EmuSync server. Is it running?", err=True)
        sys.exit(1)

    devices = client.list_devices()
    if not devices:
        click.echo("No devices configured.")
        return

    rows = []
    for device in devices:
        consoles = client.get_device_consoles(device["id"])
        for c in consoles:
            rows.append([
                c["console_name"],
                device["name"],
                c.get("device_emulator") or '-',
                c.get("device_game_folder") or '-',
                c.get("device_save_folder") or '-',
                c.get("device_state_folder") or '-',
            ])

    if not rows:
        click.echo("No consoles configured.")
        return

    headers = ["Console", "Device", "Emulator/Core", "ROM Path", "Save Path", "State Path"]
    _print_table(headers, rows)


@console.command("import")
def console_import() -> None:
    """Interactive wizard to bulk-import ROMs for a console (mirrors the GUI Add Console wizard)."""
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
        except Exception as exc:
            click.echo(f"error ({exc})")
            errors.append(entry["name"])

    click.echo(f"\nDone. {len(to_import) - len(errors)}/{len(to_import)} imported.")
    if errors:
        click.echo(f"Failed: {', '.join(errors)}")
