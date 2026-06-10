"""`server` command group — server lifecycle, mDNS, and the embedded transfer daemon."""
from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

import click

import server.config as cfg_module

from cli.common import _client
from cli.consoles_data import _prepare_console_seed_data
from cli.root import cli
from cli.transfer import _run_transfer_daemon


@cli.group()
def server() -> None:
    """Manage the EmuSync server."""


class _TimestampedStream:
    """Wrap a text stream so every new line written gets a '[YYYY-MM-DD HH:MM:SS] '
    prefix. Installed over ``sys.stdout`` at server start so all server log lines
    — current and future, from any thread — are timestamped uniformly.

    Thread-safe (writes are serialized) and ``\\r``-aware, so carriage-return
    progress updates re-stamp cleanly instead of mangling the line.
    """

    def __init__(self, stream) -> None:
        self._stream = stream
        self._at_line_start = True
        self._lock = threading.Lock()

    @staticmethod
    def _stamp() -> str:
        return datetime.now().strftime("[%Y-%m-%d %H:%M:%S] ")

    def write(self, data) -> int:
        if not isinstance(data, str):
            try:
                data = data.decode()
            except Exception:
                data = str(data)
        if not data:
            return 0
        out: list[str] = []
        with self._lock:
            for ch in data:
                if self._at_line_start and ch not in ("\n", "\r"):
                    out.append(self._stamp())
                    self._at_line_start = False
                out.append(ch)
                if ch in ("\n", "\r"):
                    self._at_line_start = True
            self._stream.write("".join(out))
        return len(data)

    def flush(self) -> None:
        self._stream.flush()

    def __getattr__(self, name):
        return getattr(self._stream, name)


def _install_timestamped_stdout() -> None:
    """Route server stdout through the timestamping wrapper (idempotent)."""
    if not isinstance(sys.stdout, _TimestampedStream):
        sys.stdout = _TimestampedStream(sys.stdout)


def _find_pid_by_port(port: int) -> int | None:
    """Return the PID of the process listening on *port*, or None if not found.

    Tries ss (iproute2) first, then lsof as a fallback.
    """
    try:
        out = subprocess.check_output(
            ["ss", "-Hlntp", f"sport = :{port}"],
            text=True, timeout=3, stderr=subprocess.DEVNULL,
        )
        m = re.search(r"pid=(\d+)", out)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    try:
        out = subprocess.check_output(
            ["lsof", f"-ti:{port}", "-sTCP:LISTEN"],
            text=True, timeout=3, stderr=subprocess.DEVNULL,
        )
        pids = out.strip().split()
        if pids:
            return int(pids[0])
    except Exception:
        pass
    return None


def _is_server_running(data_dir: str) -> tuple[bool, int | None]:
    """Check if a server is already running on this device.

    Returns (is_running, pid) where pid is the process ID if running, else None.
    """
    pid_file = Path(data_dir) / ".server_pid"
    if not pid_file.exists():
        return False, None

    try:
        pid = int(pid_file.read_text().strip())
        # Check if process exists by sending signal 0 (no-op)
        os.kill(pid, 0)
        return True, pid
    except (ValueError, FileNotFoundError, ProcessLookupError):
        # File doesn't exist, is invalid, or process is gone
        pid_file.unlink(missing_ok=True)
        return False, None


def _initialize_server_interactive(cfg: cfg_module.Config) -> cfg_module.Config:
    """Interactively initialize the server with user input.

    Prompts the user to set a PIN and confirm the port. Returns updated config.
    """
    click.echo("\n" + "=" * 60)
    click.echo("EmuSync Server Initialization")
    click.echo("=" * 60)
    click.echo(f"Device name: {cfg.device_name}")
    click.echo(f"Data directory: {cfg.data_dir}")
    click.echo()

    # Set PIN
    pin = click.prompt(
        "Enter a PIN for this server (leave blank for open access)",
        default="",
        show_default=False,
        type=str,
    ).strip()
    cfg.server_pin = pin

    # Confirm port
    default_port = cfg.server_port
    port_input = click.prompt(
        f"Server port",
        default=default_port,
        type=int,
    )
    cfg.server_port = port_input

    cfg.is_server = True
    cfg_module.save(cfg)

    click.echo("\n✓ Server initialized.")
    click.echo(f"  PIN: {'(open access)' if not pin else '***'}")
    click.echo(f"  Port: {cfg.server_port}")
    click.echo()

    return cfg


def _do_start_server() -> None:
    """Core logic to start the EmuSync server.

    Performs initialization check, duplicate-launch detection, and runs uvicorn.
    """
    import signal
    import uvicorn
    from server.store import Store
    from server import api as api_module
    from server import mdns as mdns_module

    # Timestamp every line the server writes to stdout (idempotent).
    _install_timestamped_stdout()

    cfg = cfg_module.load()

    # Check if server needs initialization
    if not cfg.is_server:
        click.echo("Server not yet initialized on this device.")
        should_init = click.confirm("Initialize now?", default=True)
        if not should_init:
            click.echo("Cancelled.")
            sys.exit(0)
        cfg = _initialize_server_interactive(cfg)

    # Check if server is already running via PID file
    is_running, running_pid = _is_server_running(cfg.data_dir)
    if is_running:
        click.echo(f"EmuSync server is already running (PID: {running_pid})")
        click.echo(f"  on :{cfg.server_port}")
        sys.exit(0)

    # Fallback: port probe catches the case where the PID file was cleaned up
    # externally (e.g. SIGKILL skipped the finally block) but the server is still bound.
    import socket as _socket
    with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as _s:
        _s.settimeout(0.5)
        if _s.connect_ex(("localhost", cfg.server_port)) == 0:
            click.echo(f"EmuSync server is already running on :{cfg.server_port}")
            sys.exit(0)

    store = Store(cfg.data_dir)
    seed_data = _prepare_console_seed_data()
    store.seed_console_defs(seed_data)
    master_token = cfg.server_pin
    token_file = Path(cfg.data_dir) / ".server_token"
    pid_file = Path(cfg.data_dir) / ".server_pid"
    token_file.write_text(master_token)
    pid_file.write_text(str(os.getpid()))
    api_module.init(store, master_token, cfg.data_dir)
    store.log_event("server_started")

    # Print token immediately so Electron can resolve server.start() without
    # waiting for mDNS registration (which can take several hundred ms).
    click.echo("EmuSync server ready")
    sys.stdout.flush()
    click.echo(f"EmuSync server running on :{cfg.server_port}")

    # Advertise via mDNS in a background thread so it doesn't block uvicorn startup.
    zc = None
    info = None
    _mdns_lock = threading.Lock()

    def _advertise_mdns() -> None:
        nonlocal zc, info
        try:
            _zc, _info = mdns_module.advertise(cfg.device_name, cfg.server_port)
            with _mdns_lock:
                zc, info = _zc, _info
        except Exception as e:
            click.echo(
                f"Warning: mDNS registration failed ({e}). Server will work without LAN discovery.",
                err=True,
            )

    mdns_thread = threading.Thread(target=_advertise_mdns, daemon=True)
    mdns_thread.start()

    _daemon_shutdown = threading.Event()

    def _start_daemon_for_server() -> None:
        """Wait for the server to be ready, then handle ROM transfers for this device."""
        import time
        client = _client(cfg)
        for _ in range(60):
            if _daemon_shutdown.is_set():
                return
            if client.health():
                break
            time.sleep(0.5)
        else:
            return
        _run_transfer_daemon(
            client, cfg.device_name,
            log=lambda msg: print(msg, flush=True),
            shutdown_event=_daemon_shutdown,
        )

    daemon_thread = threading.Thread(target=_start_daemon_for_server, daemon=True)
    daemon_thread.start()

    import logging

    class _SuppressSSECancelFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            msg = record.getMessage() + str(record.exc_info or "")
            return "CancelledError" not in msg

    logging.getLogger("uvicorn.error").addFilter(_SuppressSSECancelFilter())

    try:
        uvicorn.run(api_module.app, host="0.0.0.0", port=cfg.server_port, log_level="warning")
    finally:
        _daemon_shutdown.set()
        mdns_thread.join(timeout=2)
        with _mdns_lock:
            if zc and info:
                zc.unregister_service(info)
                zc.close()
        token_file.unlink(missing_ok=True)
        pid_file.unlink(missing_ok=True)


@server.command("start")
def server_start() -> None:
    """Start the EmuSync server and print the pairing token."""
    _do_start_server()


def _do_stop_server() -> None:
    """Core logic to stop the running server process."""
    cfg = cfg_module.load()
    is_running, pid = _is_server_running(cfg.data_dir)

    if not is_running:
        # PID file missing or stale — try to find the process by port
        pid = _find_pid_by_port(cfg.server_port)
        if pid is None:
            click.echo("server not running")
            return

    try:
        os.kill(pid, signal.SIGKILL)
        click.echo(f"Server (PID {pid}) stopped.")
        # Clean up PID file
        pid_file = Path(cfg.data_dir) / ".server_pid"
        pid_file.unlink(missing_ok=True)
    except ProcessLookupError:
        click.echo("server not running")
        # Clean up stale PID file
        pid_file = Path(cfg.data_dir) / ".server_pid"
        pid_file.unlink(missing_ok=True)
    except Exception as e:
        click.echo(f"Error stopping server: {e}", err=True)


@server.command("stop")
def server_stop() -> None:
    """Stop the running server process."""
    _do_stop_server()


@server.command("restart")
def server_restart() -> None:
    """Stop the running server, then start it again."""
    _do_stop_server()
    click.echo()  # blank line for readability
    _do_start_server()


@server.command("clear-devices")
def server_clear_devices() -> None:
    """Remove all paired devices so they must re-pair with the new PIN."""
    from server.store import Store
    cfg = cfg_module.load()
    store = Store(cfg.data_dir)
    store.clear_devices()
    click.echo("All paired devices removed.")


@server.command("discover-json")
def server_discover_json() -> None:
    """Discover EmuSync servers on the LAN and output as JSON."""
    import json
    from server import mdns as mdns_module
    results = mdns_module.discover(timeout=2.0)
    click.echo(json.dumps([{"name": r.name, "host": r.host, "port": r.port} for r in results]))
