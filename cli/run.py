"""`run` command — pull save → launch emulator → push save. Used as a Steam/launch wrapper.

Also owns the SIGTERM handler that kills the emulator child before exiting; the
handler is registered at import time so it is active for the running process.
"""
from __future__ import annotations

import hashlib
import os
import signal
import subprocess
import sys
from pathlib import Path

import click

import server.config as cfg_module
from server.sync_client import GameDeviceConfig

from cli.common import _client, _get_device_name, _show_game_running_popup
from cli.root import cli

# Track the emulator child process so SIGTERM can kill it before exiting
_child_proc: subprocess.Popen | None = None  # type: ignore[type-arg]


def _sigterm_handler(*_) -> None:
    if _child_proc is not None and _child_proc.poll() is None:
        _child_proc.kill()
    sys.exit(0)


signal.signal(signal.SIGTERM, _sigterm_handler)


def _find_save_or_state_file(configured_path: str) -> str | None:
    """Look for save/state files with different extensions. Return path if found, None if not."""
    if not configured_path:
        return None
    p = Path(configured_path)
    if p.exists():
        return configured_path
    dir_path = p.parent
    base_name = p.stem
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

    exit_code = 0
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
            sp = Path(state_path)
            if sp.is_dir():
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
    finally:
        _release()
        game_pid_file.unlink(missing_ok=True)

    sys.exit(exit_code)
