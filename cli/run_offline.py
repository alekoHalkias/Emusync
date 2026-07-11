"""Offline-launch fallback, game-device cache, and offline-play logging for
`emusync run` (split out of cli/run.py, issue #368)."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click

from server.sync_client import GameDeviceConfig

logger = logging.getLogger("emusync.run")

# Track the emulator child process so SIGTERM can kill it before exiting. Shared
# with cli.run, which registers the SIGTERM handler that reads this.
_child_proc: subprocess.Popen | None = None  # type: ignore[type-arg]


def _launch_and_wait(command: tuple[str, ...], game_pid_file: Path) -> int:
    """Spawn the emulator, record its PID, and block until it exits."""
    global _child_proc
    _child_proc = subprocess.Popen(list(command))
    game_pid_file.write_text(f"{os.getpid()}\n{_child_proc.pid}")
    code = _child_proc.wait()
    _child_proc = None
    return code


def _cache_game_device(cfg, game_slug: str, gd: GameDeviceConfig,
                        game_name: str = "", console: str = "") -> None:
    """Persist this device's game config so an offline launch knows the paths
    (the authoritative config lives on the server).

    Also updates a small sibling index (`_offline_index.json`, slug -> name/console)
    so the GUI can build an offline game list when it can't reach the server at all
    (issue #383) — kept separate from the per-slug cache file since that file is
    deserialized straight into `GameDeviceConfig` and can't carry extra keys.
    """
    try:
        path = Path(cfg.data_dir) / "game_cache" / f"{game_slug}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "rom_path": gd.rom_path,
            "save_path": gd.save_path,
            "launch_command": gd.launch_command,
            "state_path": gd.state_path,
            "rom_folder_path": gd.rom_folder_path,
            "rom_source": gd.rom_source,
            "rom_rel_path": gd.rom_rel_path,
            "local_rom_path": gd.local_rom_path,
            "rom_sha256": gd.rom_sha256,
        }))
    except Exception:
        # Non-fatal: a missing cache only means a later offline launch can't
        # resolve this game's paths (issue #241).
        logger.warning("failed to cache game config for '%s'", game_slug, exc_info=True)
        return
    if not game_name and not console:
        return
    try:
        index_path = Path(cfg.data_dir) / "game_cache" / "_offline_index.json"
        index = json.loads(index_path.read_text()) if index_path.exists() else {}
        if not isinstance(index, dict):
            index = {}
        index[game_slug] = {"name": game_name, "console": console}
        index_path.write_text(json.dumps(index))
    except Exception:
        logger.warning("failed to update offline game index for '%s'", game_slug, exc_info=True)


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


def _run_offline(cfg, game_slug: str, game_pid_file: Path, command: tuple[str, ...] = ()) -> None:
    """Server unreachable: launch the game anyway and record the play window so a
    newer offline save can win the next time the device is online.

    Offline, "imported" means a config was cached on a previous online launch — so
    a game never played online (and thus unknown to EmuSync here) is refused, just
    like the online path. The launch command comes from the cached config, unless
    an explicit `command` is passed (the old-method fallback), which then wins.
    """
    from cli.run import _resolve_launch_command

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
        launch_command = _resolve_launch_command(cached)
        if launch_command is None:
            click.echo(
                f"Offline and the ROM for '{game_slug}' is unavailable: the network "
                f"share is unreachable and there's no local copy. Localize it while "
                f"on the network so it can be played offline.",
                err=True,
            )
            sys.exit(1)
        launch_argv = tuple(shlex.split(launch_command))
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
