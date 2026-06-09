"""`run` command — pull save → launch emulator → push save. Used as a Steam/launch wrapper.

Also owns the SIGTERM handler that kills the emulator child before exiting; the
handler is registered at import time so it is active for the running process.
"""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

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


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp to an aware UTC datetime, or None."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _decide_save_action(
    local_hash: Optional[str],
    local_mtime: Optional[datetime],
    server_meta: Optional[dict],
) -> str:
    """Pre-launch save reconciliation policy — returns 'push' | 'pull' | 'noop'.

    `local_hash` is None when there is no local save; `server_meta` is the
    `get_save_meta` dict ({hash, pushed_at}) or None. On a true divergence
    (both sides changed) the newer timestamp wins — the loser is preserved as a
    `.bak` by pull_save's caller — so a newer local save is never clobbered by an
    older server one (issue #5).
    """
    if local_hash is None:
        return "pull" if server_meta else "noop"
    if not server_meta:
        return "push"  # server has no save — local is authoritative
    if local_hash == server_meta.get("hash"):
        return "noop"  # identical content
    server_time = _parse_iso(server_meta.get("pushed_at"))
    if server_time is None or (local_mtime is not None and local_mtime > server_time):
        return "push"
    return "pull"


def _notify(title: str, msg: str) -> None:
    """Best-effort, non-blocking desktop notification (so a Steam launch, which
    shows no terminal, still surfaces a conflict). Silently no-ops if unavailable."""
    try:
        subprocess.Popen(
            ["notify-send", "--app-name=EmuSync", "--urgency=critical", title, msg],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def _log_save_conflict(cfg, game_slug: str, winner: str, local_hash: Optional[str], server_meta: Optional[dict]) -> None:
    """Append a record of an auto-resolved save divergence to save_conflicts.json."""
    entry = {
        "slug": game_slug,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
        "winner": winner,  # "local" or "server"
        "local_hash": local_hash,
        "server_hash": server_meta.get("hash") if server_meta else None,
        "server_pushed_at": server_meta.get("pushed_at") if server_meta else None,
    }
    path = Path(cfg.data_dir) / "save_conflicts.json"
    try:
        existing = json.loads(path.read_text()) if path.exists() else []
        if not isinstance(existing, list):
            existing = []
    except Exception:
        existing = []
    existing.append(entry)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(existing, indent=2))
    except Exception:
        pass


def _warn_save_conflict(cfg, game_slug: str, winner: str, local_hash: Optional[str], server_meta: Optional[dict]) -> None:
    """Surface an auto-resolved divergence: stderr + desktop notification + log."""
    if winner == "local":
        detail = ("this device's save is newer, so it was kept and pushed; the server's "
                  "older copy was replaced (its hash is recorded in save_conflicts.json)")
    else:
        detail = ("the server's save is newer, so it was pulled; this device's previous "
                  "save was backed up to a .bak file next to it")
    msg = (f"Save conflict for '{game_slug}': both copies changed since the last sync — {detail}.")
    click.echo(f"⚠ {msg}", err=True)
    _log_save_conflict(cfg, game_slug, winner, local_hash, server_meta)
    _notify("EmuSync — save conflict resolved", msg)


def _reconcile_save(client, cfg, game_slug: str, save_path: str) -> Optional[str]:
    """Reconcile the local save with the server's before launch.

    Returns the hash now authoritative on the server, for the post-game
    push-if-changed comparison. When both copies diverged (a true conflict) the
    auto-resolution is surfaced loudly via _warn_save_conflict.
    """
    p = Path(save_path)
    try:
        meta = client.get_save_meta(game_slug)
    except Exception:
        meta = None

    local_hash: Optional[str] = None
    local_mtime: Optional[datetime] = None
    if p.exists():
        local_hash = hashlib.sha256(p.read_bytes()).hexdigest()
        local_mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)

    # A true divergence = both sides have a save and they differ.
    diverged = local_hash is not None and meta is not None and local_hash != meta.get("hash")

    action = _decide_save_action(local_hash, local_mtime, meta)
    if action == "push":
        client.push_save(game_slug, save_path)
        if diverged:
            _warn_save_conflict(cfg, game_slug, "local", local_hash, meta)
        else:
            click.echo(f"Local save is newer — pushed {game_slug} to server.")
        return local_hash
    if action == "pull":
        pulled, server_hash = client.pull_save(game_slug, save_path)
        if diverged:
            _warn_save_conflict(cfg, game_slug, "server", local_hash, meta)
        elif pulled:
            click.echo(f"Pulled save for {game_slug}.")
        return server_hash
    return meta.get("hash") if meta else local_hash


def _cache_game_device(cfg, game_slug: str, gd: GameDeviceConfig) -> None:
    """Persist this device's game config so an offline launch knows the paths
    (the authoritative config lives on the server)."""
    try:
        path = Path(cfg.data_dir) / "game_cache" / f"{game_slug}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "rom_path": gd.rom_path,
            "save_path": gd.save_path,
            "launch_command": gd.launch_command,
            "state_path": gd.state_path,
            "rom_folder_path": gd.rom_folder_path,
        }))
    except Exception:
        pass


def _load_cached_game_device(cfg, game_slug: str) -> Optional[GameDeviceConfig]:
    try:
        path = Path(cfg.data_dir) / "game_cache" / f"{game_slug}.json"
        if path.exists():
            return GameDeviceConfig(**json.loads(path.read_text()))
    except Exception:
        pass
    return None


def _log_offline_play(cfg, game_slug: str, started_at: str, ended_at: str, save_path: str) -> None:
    """Append a record of an offline play to ~/.emusync/offline_plays.json so a
    later online sync has a timestamped trail for conflict resolution (issue #5)."""
    entry = {"slug": game_slug, "started_at": started_at, "ended_at": ended_at, "offline": True}
    try:
        sp = Path(save_path) if save_path else None
        if sp and sp.exists():
            entry["save_mtime"] = datetime.fromtimestamp(sp.stat().st_mtime, tz=timezone.utc).isoformat()
            entry["save_hash"] = hashlib.sha256(sp.read_bytes()).hexdigest()
    except Exception:
        pass
    log_path = Path(cfg.data_dir) / "offline_plays.json"
    try:
        existing = json.loads(log_path.read_text()) if log_path.exists() else []
        if not isinstance(existing, list):
            existing = []
    except Exception:
        existing = []
    existing.append(entry)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(json.dumps(existing, indent=2))
    except Exception:
        pass


def _launch_and_wait(command: tuple[str, ...], game_pid_file: Path) -> int:
    """Spawn the emulator, record its PID, and block until it exits."""
    global _child_proc
    _child_proc = subprocess.Popen(list(command))
    game_pid_file.write_text(f"{os.getpid()}\n{_child_proc.pid}")
    code = _child_proc.wait()
    _child_proc = None
    return code


def _run_offline(cfg, game_slug: str, game_pid_file: Path, command: tuple[str, ...] = ()) -> None:
    """Server unreachable: launch the game anyway and record the play window so a
    newer offline save can win the next time the device is online.

    Offline, "imported" means a config was cached on a previous online launch — so
    a game never played online (and thus unknown to EmuSync here) is refused, just
    like the online path. The launch command comes from the cached config, unless
    an explicit `command` is passed (the old-method fallback), which then wins.
    """
    cached = _load_cached_game_device(cfg, game_slug)
    if not cached or not cached.save_path:
        click.echo(
            f"EmuSync server unreachable and '{game_slug}' has no cached config "
            f"(it hasn't been imported / played online here), so it won't be launched.",
            err=True,
        )
        sys.exit(1)
    if command:
        launch_argv = command
    elif cached.launch_command:
        launch_argv = tuple(shlex.split(cached.launch_command))
    else:
        click.echo(
            f"EmuSync server unreachable and no cached launch command for '{game_slug}'. "
            f"Launch it once while online first so the command can be cached.",
            err=True,
        )
        sys.exit(1)
    click.echo(
        "EmuSync server unreachable — launching offline. Your save will sync on the next online launch.",
        err=True,
    )
    save_path = cached.save_path
    started_at = datetime.now(timezone.utc).isoformat()
    game_pid_file.write_text(str(os.getpid()))
    exit_code = 0
    try:
        exit_code = _launch_and_wait(launch_argv, game_pid_file)
    except Exception as exc:
        click.echo(f"Emulator error: {exc}", err=True)
        game_pid_file.unlink(missing_ok=True)
        sys.exit(1)
    ended_at = datetime.now(timezone.utc).isoformat()
    _log_offline_play(cfg, game_slug, started_at, ended_at, save_path)
    game_pid_file.unlink(missing_ok=True)
    sys.exit(exit_code)


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
        launch_argv = tuple(shlex.split(gd.launch_command))

    # Cache the config so a future offline launch knows the paths + command.
    _cache_game_device(cfg, game_slug, gd)

    save_path = gd.save_path

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
        server_hash = _reconcile_save(client, cfg, game_slug, save_path)

        # Pull state if configured
        state_path = gd.state_path
        server_state_hash = None
        if state_path:
            pulled, server_state_hash = client.pull_state(game_slug, state_path)
            if pulled:
                click.echo(f"Pulled state for {game_slug}.")

        try:
            exit_code = _launch_and_wait(launch_argv, game_pid_file)
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
