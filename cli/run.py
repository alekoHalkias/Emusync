"""`run` command — pull save → launch emulator → push save. Used as a Steam/launch wrapper.

Also owns the SIGTERM handler that kills the emulator child before exiting; the
handler is registered at import time so it is active for the running process.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shlex
import signal
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click

import server.config as cfg_module
from server.store import LOCK_TTL_HOURS
from server.sync_client import GameDeviceConfig

from cli.common import _client, _get_device_name, _show_game_running_popup
from cli.root import cli

logger = logging.getLogger("emusync.run")

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
    shows no terminal, still surfaces a conflict). Silently no-ops if unavailable.

    Uses normal urgency + a 3 s expire time so the toast auto-dismisses (issue
    #218) — `critical` urgency would make compositors keep it on screen forever.
    """
    try:
        subprocess.Popen(
            ["notify-send", "--app-name=EmuSync", "--urgency=normal", "-t", "3000", title, msg],
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
        logger.debug("could not read existing %s; starting fresh", path, exc_info=True)
        existing = []
    existing.append(entry)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(existing, indent=2))
    except Exception:
        logger.warning("failed to write save conflict log %s", path, exc_info=True)


# A post-game save that is empty, or has shrunk to below this fraction of the
# previous server copy, is treated as corruption (e.g. a crashed/force-killed
# emulator left a truncated file) and is NOT pushed, so it can't destroy the good
# server copy (issue #213). SRAM is fixed-size, so a legitimate save never trips
# this; the floor is deliberately generous to avoid false positives.
_SAVE_SHRINK_FLOOR = 0.5


def _save_is_safe_to_push(local_size: int, server_size: Optional[int], floor: float = _SAVE_SHRINK_FLOOR) -> bool:
    """Whether a freshly-written save is safe to push over the server's copy.

    Refuses a 0-byte save outright, and refuses one that has shrunk below *floor*
    of the previous server save (a strong truncation signal). When the server has
    no prior save, any non-empty save is allowed (it's the first one).
    """
    if local_size <= 0:
        return False
    if not server_size or server_size <= 0:
        return True
    return local_size >= server_size * floor


def _warn_unsafe_save(cfg, game_slug: str, local_size: int, server_size: Optional[int]) -> None:
    """Surface a refused (likely-truncated) save: stderr + desktop notification."""
    detail = (
        f"the save written this session is {local_size} bytes"
        + (f" (was {server_size} bytes)" if server_size else "")
        + " — it looks truncated/corrupt, so it was NOT pushed. The good server copy "
        "was kept. If this was intentional, re-save in the emulator and play again."
    )
    msg = f"Refused to sync save for '{game_slug}': {detail}"
    click.echo(f"⚠ {msg}", err=True)
    _notify("EmuSync — save not synced", msg)


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
        # Non-fatal: a missing cache only means a later offline launch can't
        # resolve this game's paths (issue #241).
        logger.warning("failed to cache game config for '%s'", game_slug, exc_info=True)


def _load_cached_game_device(cfg, game_slug: str) -> Optional[GameDeviceConfig]:
    try:
        path = Path(cfg.data_dir) / "game_cache" / f"{game_slug}.json"
        if path.exists():
            return GameDeviceConfig(**json.loads(path.read_text()))
    except Exception:
        logger.debug("could not load cached game config for '%s'", game_slug, exc_info=True)
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
        logger.debug("could not stat/hash offline save %s", save_path, exc_info=True)
    log_path = Path(cfg.data_dir) / "offline_plays.json"
    try:
        existing = json.loads(log_path.read_text()) if log_path.exists() else []
        if not isinstance(existing, list):
            existing = []
    except Exception:
        logger.debug("could not read existing %s; starting fresh", log_path, exc_info=True)
        existing = []
    existing.append(entry)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(json.dumps(existing, indent=2))
    except Exception:
        logger.warning("failed to write offline play log %s", log_path, exc_info=True)


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


# RetroArch names save/state files after the *content name*, which differs by
# launch method: the ROM filename when loaded by path, or the database/playlist
# label when loaded from a scanned playlist (e.g. "Pokémon Pinball_ Ruby &
# Sapphire [2003]"). So the real save/state may sit in a different folder AND/OR
# under a different extension than we configured. After the emulator exits we
# detect where it actually wrote *this session* and adopt that path (issue #210).
_SAVE_EXTS = {"srm", "sav", "save", "fla", "eep", "mcr", "rtc", "dsv", "ss0"}
_STATE_RE = re.compile(r"\.state(\d+|\.auto)?$", re.IGNORECASE)


def _mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def _saves_root(save_path: str) -> Path:
    """Directory tree to search for the real save. Saves use the content-dir
    layout savesRoot/<content>/<content>.<ext>, so the root is two levels up;
    fall back to one level for flat layouts."""
    parent = Path(save_path).parent
    grand = parent.parent
    return grand if grand != parent else parent


def _newest_matching(root: Path, since: float, match) -> Optional[Path]:
    """Newest file under *root* (recursively) modified at/after *since* for which
    match(file) is truthy, or None."""
    if not root.exists():
        return None
    best: Optional[Path] = None
    best_m = since
    for f in root.rglob("*"):
        try:
            if not f.is_file() or not match(f):
                continue
            m = _mtime(f)
        except OSError:
            continue
        if m >= since and (best is None or m > best_m):
            best, best_m = f, m
    return best


def _resolve_written_save(configured: str, since: float) -> Optional[str]:
    """The save file RetroArch actually wrote this session, or None if none was.

    Conservative: if our configured save was written this session, keep it. Only
    when it was *not* (RetroArch used a different content name) do we adopt the
    newest save written elsewhere under the saves root — so a working config is
    never disturbed. Also catches a same-folder extension change for free.
    """
    if not configured:
        return None
    p = Path(configured)
    if p.exists() and _mtime(p) >= since:
        return configured
    found = _newest_matching(
        _saves_root(configured), since,
        lambda f: f.suffix.lstrip(".").lower() in _SAVE_EXTS and ".bak" not in f.suffixes,
    )
    return str(found) if found else None


def _resolve_written_state(configured: str, since: float) -> Optional[str]:
    """The state FOLDER RetroArch actually wrote this session, or None.

    States are synced as a whole folder, so this returns a directory. Same
    conservative policy as _resolve_written_save: keep the configured folder if it
    was written, else adopt the folder containing the newest state file.
    """
    if not configured:
        return None
    folder = Path(configured)
    if folder.is_dir() and any(
        _mtime(f) >= since for f in folder.rglob("*") if f.is_file()
    ):
        return configured
    found = _newest_matching(folder.parent, since, lambda f: bool(_STATE_RE.search(f.name)))
    return str(found.parent) if found else None


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
        # name = ROM filename vs database label) — and adopt that path.
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
            local_bytes = Path(save_path).read_bytes()
            local_hash = hashlib.sha256(local_bytes).hexdigest()
            if local_hash != server_hash:
                # Guard against pushing a truncated/zero-byte save from a crashed
                # emulator over the good server copy (issue #213).
                server_size: Optional[int] = None
                try:
                    sm = client.get_save_meta(game_slug)
                    server_size = sm.get("size") if sm else None
                except Exception:
                    server_size = None
                if _save_is_safe_to_push(len(local_bytes), server_size):
                    try:
                        client.push_save(game_slug, save_path)
                        click.echo(f"Pushed save for {game_slug}.")
                    except Exception as exc:
                        click.echo(f"Warning: failed to push save: {exc}", err=True)
                else:
                    _warn_unsafe_save(cfg, game_slug, len(local_bytes), server_size)

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
