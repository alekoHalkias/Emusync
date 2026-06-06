"""Shared helpers used across CLI command modules."""
from __future__ import annotations

import subprocess

import click

import server.config as cfg_module
from server.sync_client import SyncClient


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
        ["notify-send", "--app-name=EmuSync", "--urgency=normal", "EmuSync", msg],
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
