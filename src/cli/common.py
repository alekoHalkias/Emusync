"""Shared helpers used across CLI command modules."""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click

import server.config as cfg_module
from server.sync_client import SyncClient


def split_launch_command(cmd: str, windows: Optional[bool] = None) -> list[str]:
    """Split a stored launch command into argv (#702).

    Windows keeps backslashes (non-POSIX tokenizing, quotes stripped). A stored
    command whose executable path has spaces but was never quoted (pre-#702) is
    repaired by joining the shortest run of leading tokens that is a real file.
    """
    if windows is None:
        windows = os.name == "nt"
    if windows:
        argv = [t[1:-1] if len(t) > 1 and t[0] == t[-1] and t[0] in "\"'" else t
                for t in shlex.split(cmd, posix=False)]
    else:
        argv = shlex.split(cmd)
    if argv and not (os.path.isfile(argv[0]) or shutil.which(argv[0])):
        for i in range(2, len(argv) + 1):
            if os.path.isfile(" ".join(argv[:i])):
                return [" ".join(argv[:i])] + argv[i:]
    return argv


def _parse_iso_utc(iso: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp to an aware UTC datetime, or None.

    All EmuSync timestamps are UTC; a value with no tz designator is assumed UTC.
    """
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _relative(dt_utc: datetime, now: datetime) -> str:
    """Human relative phrase, e.g. 'just now', '2 hours ago', 'in 3 minutes'."""
    sec = (now - dt_utc).total_seconds()
    future = sec < 0
    sec = abs(sec)
    if sec < 45:
        return "just now"
    for name, size in (("year", 31536000), ("month", 2592000), ("week", 604800),
                       ("day", 86400), ("hour", 3600), ("minute", 60)):
        if sec >= size:
            n = int(round(sec / size))
            label = f"{n} {name}{'s' if n != 1 else ''}"
            return f"in {label}" if future else f"{label} ago"
    return "just now"


def _fmt_time(iso: Optional[str]) -> str:
    """Render a timestamp as '<relative> (<exact local 12h>)' for CLI output.

    The CLI can't show a hover tooltip like the GUI, so the exact local time is
    appended in parentheses (issue #216). Returns the raw value (or '?') if it
    can't be parsed.
    """
    dt = _parse_iso_utc(iso)
    if dt is None:
        return iso or "?"
    rel = _relative(dt, datetime.now(timezone.utc))
    local = dt.astimezone()  # convert to the machine's local timezone
    hour = local.strftime("%I").lstrip("0") or "12"
    exact = f"{local.strftime('%b')} {local.day} {local.year}, {hour}:{local.strftime('%M %p')}"
    return f"{rel} ({exact})"


def _client(cfg=None) -> SyncClient:
    if cfg is None:
        cfg = cfg_module.load()
    host = cfg.server_host or "localhost"
    return SyncClient(host, cfg.server_port, cfg.server_pin, cfg.device_id, cfg.device_name)


def _get_device_name(client: SyncClient, device_id: str) -> str:
    """Return the display name for a device ID, or the ID itself as fallback."""
    try:
        devices = client.list_devices()
        for d in devices:
            if d.get("id") == device_id:
                return d.get("name", device_id)
    except Exception:
        pass
    return device_id


def _print_table(headers: list[str], rows: list[list]) -> None:
    """Print a left-aligned text table with a header separator."""
    n = len(headers)
    col_widths = [max(len(headers[i]), max((len(str(row[i])) for row in rows), default=0)) for i in range(n)]
    click.echo("  ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers)))
    click.echo("  ".join("-" * w for w in col_widths))
    for row in rows:
        click.echo("  ".join(str(row[i]).ljust(col_widths[i]) for i in range(n)))


def _mtime(p) -> float:
    """Return the modification time of a path, or 0.0 on error."""
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def _newest_matching(root, since, match):
    """Return the newest file under *root* (recursively) modified at/after *since*
    for which match(file) is truthy, or None."""
    if not root.exists():
        return None
    best = None
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


def _find_touched_path(configured: str, since: float, match, search_root: Optional[Path] = None, is_dir=False, parent_only=False) -> Optional[str]:
    """Return the path (file or directory) actually written this session, or None.

    Args:
        configured: The configured path (may be empty or None)
        since: Only consider modifications at/after this timestamp
        match: Function to test whether a path matches what we're looking for
        search_root: Optional base directory to search in if 'configured' wasn't touched.
                     If None, defaults to configured's parent (for files) or itself (for dirs).
        is_dir: If True, return the directory containing the match, not the file itself
        parent_only: If True, only check if the configured directory itself was touched (not its files)
    """
    if not configured:
        return None

    configured_path = Path(configured)

    # If configured is a directory and parent_only is True, just check if the directory itself
    # was modified since *since*.
    if parent_only and configured_path.is_dir():
        if _mtime(configured_path) >= since:
            return configured
        return None

    # Check if the configured file/folder was written this session.
    if is_dir:
        # Check only files directly in the directory (not subdirectories)
        if configured_path.is_dir() and any(_mtime(f) >= since for f in configured_path.iterdir() if f.is_file()):
            return configured
    else:
        if configured_path.exists() and _mtime(configured_path) >= since:
            return configured

    # Configured wasn't touched — look for the newest matching file/folder elsewhere.
    if search_root:
        root = search_root
    elif configured_path.is_dir():
        root = configured_path
    else:
        root = configured_path.parent

    found = _newest_matching(root, since, match)
    if found is None:
        return None

    # Return the directory containing the match if requested, otherwise the file itself.
    if is_dir or parent_only:
        return str(found.parent)
    return str(found)


def _show_game_running_popup(game_name: str, device_name: str) -> None:
    """Show a blocking 'game already running' dialog using the best available method.

    Tries zenity → kdialog → xmessage (all Wayland-safe) before falling back to
    tkinter, so it works even when libtk is missing or X11 is unavailable.
    """
    msg = f"{game_name} is already running.\nPlease close it on {device_name}."

    cmds = [
        # notify-send is non-blocking but works inside gamescope (Steam Deck Gaming Mode)
        # where zenity/kdialog cannot create windows; run it and also continue to a
        # blocking dialog so the user sees a modal on desktop environments too.
        # `-t 3000` auto-dismisses the toast after 3 s (issue #218); the blocking
        # dialog below is deliberate and still waits for acknowledgement.
        ["notify-send", "--app-name=EmuSync", "--urgency=normal", "-t", "3000", "EmuSync", msg],
        ["zenity", "--info", "--title=EmuSync", f"--text={msg}", "--width=360", "--no-wrap"],
        ["kdialog", "--msgbox", msg, "--title", "EmuSync"],
        ["xmessage", "-center", "-buttons", "OK:0", msg],
    ]
    notify_sent = False
    for cmd in cmds:
        is_notify = cmd[0] == "notify-send"
        try:
            subprocess.run(cmd, timeout=300)
            if is_notify:
                notify_sent = True
                continue  # always try a blocking dialog after notifying
            return
        except (FileNotFoundError, PermissionError):
            continue
        except subprocess.TimeoutExpired:
            if not is_notify:
                return

    # Last-resort tkinter (may fail on systems without libtk)
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        messagebox.showinfo("EmuSync", msg, parent=root)
        root.destroy()
    except Exception:
        pass
