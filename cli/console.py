"""`console` command group — list configured consoles and the import wizard."""
from __future__ import annotations

import os

import click

from server import config as _cfg
from server.sync_client import GameDeviceConfig

from cli.common import _client, _print_table
from cli.consoles_data import (
    _DEFAULT_SAVE_EXTS,
    _DEFAULT_STATE_EXTS,
    _IMPORT_CONSOLES,
    _IMPORT_SYSTEMS,
)
from cli.detect import (
    _detect_emulators_for_console,
    _match_save_file,
    _resolve_shared_memcard_save_state,
    _scan_rom_dir,
)
from cli.root import cli
from cli.run import _SHARED_MEMCARD_CONSOLES, _SHARED_STATE_CONSOLES


def _classify_network_roms(
    entries: list[dict],
    network_root: str,
    local_root: str,
) -> list[dict]:
    """Tag each entry as 'network', 'local', or 'both'; merge same-filename dupes.

    Mirrors classifyByRoot() in the GUI helper. A ROM under local_root is
    the local copy; everything else is treated as on the network share. When
    the same filename appears under both roots, the entries are merged into a
    single 'both' row keyed off the network copy.
    """
    lroot = local_root.rstrip("/").rstrip(os.sep) if local_root else ""
    by_filename: dict[str, dict] = {}
    for e in entries:
        key = os.path.basename(e["rom_path"]).lower()
        slot = by_filename.setdefault(key, {})
        if lroot and (
            e["rom_path"] == lroot
            or e["rom_path"].startswith(lroot + "/")
            or e["rom_path"].startswith(lroot + os.sep)
        ):
            slot["local"] = e
        else:
            slot["network"] = e
    result: list[dict] = []
    for slot in by_filename.values():
        net = slot.get("network")
        loc = slot.get("local")
        if net and loc:
            result.append({**net, "presence": "both", "local_rom_path": loc["rom_path"]})
        elif net:
            result.append({**net, "presence": "network", "local_rom_path": ""})
        elif loc:
            result.append({**loc, "presence": "local", "local_rom_path": loc["rom_path"]})
    return result


def _build_network_game_device(
    entry: dict,
    network_root: str,
    local_root: str,
) -> GameDeviceConfig:
    """Build a GameDeviceConfig for a network-sourced ROM entry.

    - 'local' presence: uploads the local file to the share as the master,
      records the local path as the already-made localized copy.
    - 'both' presence: network copy is the master, local copy already exists.
    - 'network' presence: network-only, no local copy.
    """
    from cli.netrom import compute_rel_path, upload_to_master

    presence = entry.get("presence", "network")
    local_rom_path = entry.get("local_rom_path", "")
    rom_sha = ""

    if presence == "local":
        filename = os.path.basename(local_rom_path)
        master_path = os.path.join(network_root, filename)
        up = upload_to_master(local_rom_path, master_path)
        final_rom_path = master_path
        final_local_rom_path = local_rom_path
        final_launch_cmd = entry["launch_command"].replace(entry["rom_path"], master_path)
        rom_sha = up.sha256
    else:
        final_rom_path = entry["rom_path"]
        final_local_rom_path = local_rom_path if presence == "both" else ""
        final_launch_cmd = entry["launch_command"]

    rom_rel_path = (
        compute_rel_path(network_root, final_rom_path)
        or os.path.basename(final_rom_path)
    )
    return GameDeviceConfig(
        rom_path=final_rom_path,
        save_path=entry["save_path"],
        launch_command=final_launch_cmd,
        state_path=entry.get("state_path", ""),
        rom_folder_path=network_root,
        rom_source="network",
        rom_rel_path=rom_rel_path,
        local_rom_path=final_local_rom_path,
        rom_sha256=rom_sha,
        device_network_folder=network_root,
        device_local_folder=local_root,
    )


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
                c.get("device_network_folder") or '-',
                c.get("device_local_folder") or '-',
            ])

    if not rows:
        click.echo("No consoles configured.")
        return

    headers = ["Console", "Device", "Emulator/Core", "ROM Path", "Save Path", "State Path", "Network Folder", "Local Folder"]
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
    console_key = console_def["key"]
    # Shared-save consoles (PS2/DC/GC/PSP) share one card across every game, so
    # the per-game save is resolved to that shared location rather than matched
    # by ROM filename (issue #295, #361, #402). Only PS2 also shares its STATES.
    shared_layout = console_def["abbr"] in _SHARED_MEMCARD_CONSOLES
    shared_state = console_def["abbr"] in _SHARED_STATE_CONSOLES
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

    # ── Step 3: ROM source + folder(s) ───────────────────────────────────────
    saved_cfg = _cfg.load()
    last_source = saved_cfg.import_rom_source.get(console_key, "local")
    last_local_folder = saved_cfg.import_local_folder.get(console_key, "")
    suggested_dirs = emu.get("rom_dirs", [])

    click.echo("\nROM source:")
    click.echo("  1. Local folder")
    click.echo("  2. Network / shared drive")
    src_default = 2 if last_source == "network" else 1
    src_choice = click.prompt(
        "Select source",
        type=click.IntRange(1, 2),
        default=src_default,
    )
    rom_source = "network" if src_choice == 2 else "local"

    network_root = ""
    local_root = ""

    if rom_source == "local":
        if suggested_dirs:
            click.echo(f"\nRetroArch ROM directory: {suggested_dirs[0]}")
        rom_folder = click.prompt(
            "\nPath to ROM folder",
            default=suggested_dirs[0] if suggested_dirs else "",
        ).strip()
        if not rom_folder or not os.path.isdir(rom_folder):
            click.echo("Error: folder not found.")
            return
        scan_folders = [rom_folder]
    else:
        net_default = suggested_dirs[0] if suggested_dirs else ""
        network_root = click.prompt(
            "\nNetwork ROM folder (share path on this device, e.g. /mnt/nas/roms/GBA)",
            default=net_default,
        ).strip()
        if not network_root or not os.path.isdir(network_root):
            click.echo("Error: network folder not found or not mounted.")
            return

        local_root = click.prompt(
            "Local-copy destination for offline play (optional, press Enter to skip)",
            default=last_local_folder,
        ).strip()
        if local_root and not os.path.isdir(local_root):
            if click.confirm(f"  Folder {local_root!r} doesn't exist — create it?", default=True):
                os.makedirs(local_root, exist_ok=True)
            else:
                local_root = ""

        rom_folder = network_root
        scan_folders = [network_root]
        if local_root:
            scan_folders.append(local_root)

    # ── Step 4: scan for ROMs ─────────────────────────────────────────────────
    click.echo("Scanning for ROMs and saves…")

    # `rom_extensions` is the explicit scannable-extension list for a standalone-
    # only console with no libretro core (PS2, #293); fall back to `system_keys`
    # for a RetroArch-backed console, which uses its core-derived extensions.
    rom_ext_set = set(console_def.get("rom_extensions") or console_def["system_keys"])
    all_files: list[str] = []
    for folder in scan_folders:
        all_files.extend(_scan_rom_dir(folder))
    matching = [p for p in all_files
                if os.path.splitext(p)[1].lstrip(".").lower() in rom_ext_set]

    if not matching:
        click.echo("No ROMs found.")
        return

    # Build ROM entries (same logic as main.ts emulator:scan handler)
    first_sys_key = console_def["system_keys"][0] if console_def["system_keys"] else None
    default_save_exts = _IMPORT_SYSTEMS.get(first_sys_key, {}).get("save_exts", _DEFAULT_SAVE_EXTS)
    # Console-wide, not per-game — resolve once for a shared-memcard console.
    shared_save_match, shared_state_match = (
        _resolve_shared_memcard_save_state(emu, console_def["abbr"]) if shared_layout else (None, None)
    )

    entries: list[dict] = []
    for rom_path in sorted(matching):
        ext = os.path.splitext(rom_path)[1].lstrip(".").lower()
        base = os.path.splitext(os.path.basename(rom_path))[0]

        if shared_layout:
            save_match = shared_save_match
        else:
            system = _IMPORT_SYSTEMS.get(ext, {})
            save_exts = system.get("save_exts", default_save_exts)

            save_match = _match_save_file(emu["save_dir"], base, save_exts)
            # Fallback: check root saves dir for pre-core-organisation saves
            if not save_match["exists"] and emu.get("core_folder"):
                root_save_dir = os.path.dirname(emu["save_dir"])
                root_match = _match_save_file(root_save_dir, base, save_exts)
                if root_match["exists"]:
                    save_match = root_match

        # States are per-game except for a shared-STATE console (PS2's serial-
        # named sstates/) — dc/gamecube/psp cores write normal per-content
        # states even though their saves are shared (#402).
        if shared_state:
            state_match = shared_state_match
        else:
            state_match = None
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

    # For network imports, classify each ROM as network/local/both and merge dupes.
    if rom_source == "network":
        entries = _classify_network_roms(entries, network_root, local_root)

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
    _PRESENCE_TAG = {"network": "  [network]", "local": "  [local→share]", "both": "  [network+local]"}

    click.echo(f"\nFound {len(entries)} ROM(s):\n")
    for i, e in enumerate(entries, 1):
        save_tag = "  [save found]" if e["save_exists"] else ""
        state_tag = "  [state found]" if e.get("state_path") else ""
        src_tag = _PRESENCE_TAG.get(e.get("presence", ""), "") if rom_source == "network" else ""
        click.echo(f"  {i:>3}. {e['name']}{save_tag}{state_tag}{src_tag}")

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
            if rom_source == "network":
                gd_cfg = _build_network_game_device(entry, network_root, local_root)
            else:
                gd_cfg = GameDeviceConfig(
                    rom_path=entry["rom_path"],
                    save_path=entry["save_path"],
                    launch_command=entry["launch_command"],
                    state_path=entry["state_path"],
                    rom_folder_path=entry["rom_folder_path"],
                )
            client.set_game_device(slug, gd_cfg)
            click.echo("ok")
        except Exception as exc:
            click.echo(f"error ({exc})")
            errors.append(entry["name"])

    # ── Persist source preference ─────────────────────────────────────────────
    try:
        cfg = _cfg.load()
        cfg.import_rom_source[console_key] = rom_source
        if rom_source == "network" and local_root:
            cfg.import_local_folder[console_key] = local_root
        _cfg.save(cfg)
    except Exception:
        pass

    click.echo(f"\nDone. {len(to_import) - len(errors)}/{len(to_import)} imported.")
    if errors:
        click.echo(f"Failed: {', '.join(errors)}")
    if rom_source == "network":
        click.echo("Network ROMs aren't copied to peers — every device reads from the share.")
