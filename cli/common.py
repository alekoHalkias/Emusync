"""Shared helpers used across CLI command modules."""
from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from typing import Optional

import click

import server.config as cfg_module
from server.sync_client import SyncClient


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
