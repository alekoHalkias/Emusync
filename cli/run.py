"""`run` command — pull save → launch emulator → push save. Used as a Steam/launch wrapper.

Also owns the SIGTERM handler that kills the emulator child before exiting; the
handler is registered at import time so it is active for the running process.

Split (issue #368) into: cli.run_reconcile (save/state reconcile + written-path
detection), cli.run_ps2 (PS2/PCSX2 shared-memcard/state adapter),
cli.run_conflicts (save-safety checks + conflict logging/notification),
cli.run_offline (offline fallback + game-device cache). Everything moved is
re-exported here so `from cli.run import X` keeps working for existing callers
and tests.
"""
from __future__ import annotations

import hashlib
import os
import shlex
import signal
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click

import server.config as cfg_module
from server.store import LOCK_TTL_HOURS
from server.sync_client import GameDeviceConfig, memcard_bytes

from cli.common import _client, _get_device_name, _show_game_running_popup
from cli.netrom import resolve_rom_path
from cli.root import cli

from cli import run_offline as _run_offline_mod
from cli.run_conflicts import (  # noqa: F401 — re-exported for existing callers/tests
    _log_save_conflict,
    _notify,
    _report_conflict_to_server,
    _save_is_safe_to_push,
    _warn_save_conflict,
    _warn_unsafe_save,
    _SAVE_SHRINK_FLOOR,
)
from cli.run_offline import (  # noqa: F401 — re-exported for existing callers/tests
    _cache_game_device,
    _launch_and_wait,
    _load_cached_game_device,
    _log_offline_play,
    _run_offline,
)
from cli.run_ps2 import (  # noqa: F401 — re-exported for existing callers/tests
    _MemcardClient,
    _learn_ps2_serial,
    _ps2_state_serial_prefix,
    _read_pcsx2_playtime,
    _SHARED_MEMCARD_CONSOLES,
    _SHARED_STATE_CONSOLES,
)
from cli.run_reconcile import (  # noqa: F401 — re-exported for existing callers/tests
    _decide_save_action,
    _mtime,
    _newest_matching,
    _reconcile_save,
    _resolve_written_save,
    _resolve_written_state,
    _saves_root,
    _SAVE_EXTS,
    _STATE_RE,
)


def _resolve_launch_command(gd) -> Optional[str]:
    """Return *gd*'s launch command pointed at an available ROM copy, or None.

    Local games are returned unchanged. For network-sourced games, prefer the
    live NAS master; if it's unreachable, fall back to a localized copy and
    rewrite the command to point at it. None means no ROM copy is currently
    available (mount down + no local copy) so the caller should refuse.
    """
    cmd = gd.launch_command
    if getattr(gd, "rom_source", "local") != "network":
        return cmd
    effective = resolve_rom_path(gd.rom_source, gd.rom_path, gd.local_rom_path)
    if not effective:
        return None
    if effective != gd.rom_path and gd.rom_path and cmd:
        cmd = cmd.replace(gd.rom_path, effective)
    return cmd


def _sigterm_handler(*_) -> None:
    child = _run_offline_mod._child_proc
    if child is not None and child.poll() is None:
        child.kill()
    sys.exit(0)


signal.signal(signal.SIGTERM, _sigterm_handler)


# Refresh the lock at a quarter of the TTL so a play session longer than the TTL
# never lets another device steal the lock mid-game (issue #238). A re-acquire by
# the same holder just bumps `acquired_at`, so it's a cheap keep-alive.
_HEARTBEAT_INTERVAL_SECONDS = max(60, int(LOCK_TTL_HOURS * 3600) // 4)


def _start_lock_heartbeat(client, game_slug: str, stop: threading.Event) -> threading.Thread:
    """Periodically re-acquire the lock while the game runs to keep it fresh.

    Runs until *stop* is set (i.e. the emulator exits). A failed beat is ignored —
    it's transient, and the next beat or the server-side TTL/offline reap covers it.
    """
    def _beat() -> None:
        while not stop.wait(_HEARTBEAT_INTERVAL_SECONDS):
            try:
                client.acquire_lock(game_slug)
            except Exception:
                pass
    t = threading.Thread(target=_beat, daemon=True)
    t.start()
    return t


@cli.command("run")
@click.argument("game_slug")
@click.argument("command", nargs=-1)
def run_game(game_slug: str, command: tuple[str, ...]) -> None:
    """Reconcile save, launch the emulator, push save.

    GAME_SLUG is the game's slug (from 'emusync game list'). Normally that's all
    you need — the emulator command is taken from the game's saved launch_command:

        emusync run zelda

    As a fallback for the old method, you may pass an explicit command (e.g. from
    a Steam shortcut that wraps RetroArch's own launcher via '%command%'):

        emusync run zelda -- retroarch -L mgba.so /roms/zelda.gba

    EmuSync then links that launch to the imported game and still syncs the save —
    but only if the game has been imported. If it hasn't, EmuSync refuses to launch
    it (it can't sync a game it doesn't know about).
    """
    cfg = cfg_module.load()
    client = _client(cfg)
    game_pid_file = Path(cfg.data_dir) / ".game_pid"

    # Server unreachable → launch offline and record the play window instead of
    # bailing out, so the game is still playable away from the LAN (issue #5).
    if not client.health():
        _run_offline(cfg, game_slug, game_pid_file, command)
        return  # _run_offline exits

    gd = client.get_game_device(game_slug)

    # A game is "imported" on this device when it has a save path configured (so
    # EmuSync knows what to sync). Both launch modes require this.
    if not gd or not gd.save_path:
        if command:
            # Fallback path: an external launcher tried to run a game EmuSync
            # doesn't know about — refuse, since we can't sync its save.
            click.echo(
                f"'{game_slug}' is not imported into EmuSync, so it won't be launched. "
                f"Import it first (Add Console / 'emusync console import').",
                err=True,
            )
        else:
            click.echo(
                f"No save path configured for '{game_slug}'. "
                f"Run 'emusync game edit {game_slug} --save <path>' first.",
                err=True,
            )
        sys.exit(1)

    if command:
        # Fallback (old method): honor the externally supplied command — e.g.
        # RetroArch's own launch file via a Steam '%command%' wrapper — while still
        # wrapping it in the EmuSync sync/lock flow.
        launch_argv = command
    else:
        if not gd.launch_command:
            click.echo(
                f"No launch command configured for '{game_slug}'. "
                f"Re-import the console or set it with 'emusync game edit'.",
                err=True,
            )
            sys.exit(1)
        # The emulator invocation lives in the game config — parse it into argv.
        # For a network-sourced ROM this prefers the live NAS master, falls back
        # to a localized copy, or refuses if neither is reachable.
        launch_command = _resolve_launch_command(gd)
        if launch_command is None:
            click.echo(
                f"ROM for '{game_slug}' is unavailable: the network share is "
                f"unreachable and there's no local copy. Run "
                f"'emusync rom localize {game_slug}' while on the network.",
                err=True,
            )
            sys.exit(1)
        launch_argv = tuple(shlex.split(launch_command))

    # Shared-memory-card consoles (PS2): the per-game "save" is actually one card
    # shared across the whole console, so route save reconciliation to the
    # console-scoped endpoints (keyed by console abbr) instead of this game's slug
    # (issue #295). Everything downstream uses save_client/save_key so the existing
    # newest-wins/.bak reconcile logic is reused unchanged.
    game_name = ""
    console_abbr = ""
    try:
        _g = client.get_game(game_slug)
        game_name = (_g or {}).get("name", "") or ""
        console_abbr = (_g or {}).get("console", "") or ""
    except Exception:
        game_name = ""
        console_abbr = ""

    # Cache the config so a future offline launch knows the paths + command, and
    # so the GUI can show this game while the server is unreachable (issue #383).
    _cache_game_device(cfg, game_slug, gd, game_name=game_name, console=console_abbr)

    save_path = gd.save_path
    shared_memcard = console_abbr in _SHARED_MEMCARD_CONSOLES
    save_client = _MemcardClient(client, console_abbr, cfg) if shared_memcard else client
    save_key = console_abbr if shared_memcard else game_slug
    # Whether save states live in a shared, serial-named folder (PS2 sstates/) and
    # so must be synced filtered by serial rather than as a whole folder (#294).
    shared_state = console_abbr in _SHARED_STATE_CONSOLES

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

    exit_code = 0
    game_pid_file.write_text(str(os.getpid()))
    try:
        # Reconcile the save before launch: push if the local save is newer than
        # the server's, pull if the server's is newer (newest wins; loser kept
        # as .bak). server_hash = what's authoritative on the server afterwards.
        # For a shared-memcard console this reconciles the console card (#295).
        server_hash = _reconcile_save(save_client, cfg, save_key, save_path)

        # Pull state if configured. For a shared sstates folder (PS2) use the
        # merge pull so other games' states in the folder aren't disturbed (#294).
        state_path = gd.state_path
        server_state_hash = None
        if state_path:
            if shared_state:
                pulled, server_state_hash = client.pull_state_merge(game_slug, state_path)
            else:
                pulled, server_state_hash = client.pull_state(game_slug, state_path)
            if pulled:
                click.echo(f"Pulled state for {game_slug}.")

        # Keep the lock fresh for the whole session so a long play can't have its
        # lock stolen at the TTL by another device (issue #238).
        stop_heartbeat = threading.Event()
        _start_lock_heartbeat(client, game_slug, stop_heartbeat)

        # Mark the moment before launch (minus a small epsilon for mtime
        # granularity) so we can tell which save/state files were written *this*
        # session when reconciling RetroArch's content-name folder afterwards.
        launch_start = datetime.now(timezone.utc).timestamp() - 1.0
        try:
            exit_code = _launch_and_wait(launch_argv, game_pid_file)
        except Exception as exc:
            stop_heartbeat.set()
            click.echo(f"Emulator error: {exc}", err=True)
            _release()
            sys.exit(1)
        stop_heartbeat.set()

        # Detect where RetroArch actually wrote the save/state this session — it
        # may differ in folder and/or extension from what we configured (content
        # name = ROM filename vs database label) — and adopt that path. Skipped for
        # a shared-memcard console: the card lives at a fixed path, and this
        # RetroArch content-name heuristic doesn't apply to PCSX2 (issue #295).
        if shared_memcard:
            actual_save_path = None
            actual_state_path = None
        else:
            actual_save_path = _resolve_written_save(save_path, launch_start)
            actual_state_path = _resolve_written_state(state_path, launch_start) if state_path else None

        if (actual_save_path and actual_save_path != save_path) or (actual_state_path and actual_state_path != state_path):
            try:
                updated_gd = GameDeviceConfig(
                    rom_path=gd.rom_path,
                    save_path=actual_save_path or save_path,
                    launch_command=gd.launch_command,
                    state_path=actual_state_path or state_path,
                    rom_folder_path=gd.rom_folder_path,
                    # Preserve network-ROM source fields — adopting a written
                    # save/state path must not reset rom_source to 'local' (#255).
                    rom_source=gd.rom_source,
                    rom_rel_path=gd.rom_rel_path,
                    local_rom_path=gd.local_rom_path,
                    rom_sha256=gd.rom_sha256,
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
            local_bytes = memcard_bytes(Path(save_path))
            local_hash = hashlib.sha256(local_bytes).hexdigest()
            if local_hash != server_hash:
                # Guard against pushing a truncated/zero-byte save from a crashed
                # emulator over the good server copy (issue #213). For a shared-
                # memcard console this pushes the console card (issue #295).
                server_size: Optional[int] = None
                try:
                    sm = save_client.get_save_meta(save_key)
                    server_size = sm.get("size") if sm else None
                except Exception:
                    server_size = None
                if _save_is_safe_to_push(len(local_bytes), server_size):
                    try:
                        save_client.push_save(save_key, save_path)
                        click.echo(f"Pushed save for {save_key}.")
                    except Exception as exc:
                        click.echo(f"Warning: failed to push save: {exc}", err=True)
                else:
                    _warn_unsafe_save(cfg, save_key, len(local_bytes), server_size)

        # Push state if configured
        if state_path and Path(state_path).exists():
            sp = Path(state_path)
            if shared_state:
                # Shared sstates folder (PS2): push only THIS game's serial files,
                # and only when a state was written this session (#294).
                prefix = _ps2_state_serial_prefix(state_path, launch_start)
                if prefix:
                    try:
                        client.push_state(game_slug, state_path, name_prefix=prefix)
                        click.echo(f"Pushed state for {game_slug}.")
                    except Exception as exc:
                        click.echo(f"Warning: failed to push state: {exc}", err=True)
            elif sp.is_dir():
                # For folder-based states, always push after the game exits so
                # all slots (game.state, game.state1, …) are synced.
                try:
                    client.push_state(game_slug, state_path)
                    click.echo(f"Pushed state for {game_slug}.")
                except Exception as exc:
                    click.echo(f"Warning: failed to push state: {exc}", err=True)
            else:
                local_state_hash = hashlib.sha256(sp.read_bytes()).hexdigest()
                if local_state_hash != server_state_hash:
                    try:
                        client.push_state(game_slug, state_path)
                        click.echo(f"Pushed state for {game_slug}.")
                    except Exception as exc:
                        click.echo(f"Warning: failed to push state: {exc}", err=True)

        # Learn this PS2 game's serial from PCSX2's freshly-updated playtime.dat so
        # the GUI can show a real per-game last-played despite the shared card (#301).
        if shared_memcard:
            _learn_ps2_serial(cfg, game_slug, launch_start)
    finally:
        _release()
        game_pid_file.unlink(missing_ok=True)

    sys.exit(exit_code)
