"""`server` command group — server lifecycle, mDNS, and the embedded transfer daemon."""
from __future__ import annotations

import logging
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


def _suppress_sse_cancel_log(record: logging.LogRecord) -> bool:
    """Drop uvicorn's noisy CancelledError log when an SSE stream is force-closed
    on graceful shutdown (issue #268) — expected, not an error."""
    msg = record.getMessage() + str(record.exc_info or "")
    return "CancelledError" not in msg


@cli.group()
def server() -> None:
    """Manage the EmuSync server."""


class _RotatingLogWriter:
    """Append text to a size-capped log file, rotating to numbered backups.

    When the file would exceed *max_bytes*, it is rotated: ``server.log`` →
    ``server.log.1`` → ``server.log.2`` … keeping at most *backups* old files.
    Used by :class:`_TimestampedStream` to mirror already-stamped stdout lines to
    ``~/.emusync/server.log``. Not thread-safe on its own — the caller
    (``_TimestampedStream``) serializes writes under its own lock.
    """

    def __init__(self, path: Path, max_bytes: int = 5 * 1024 * 1024, backups: int = 3) -> None:
        self._path = path
        self._max_bytes = max_bytes
        self._backups = backups
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self._path, "a", encoding="utf-8")

    def write(self, text: str) -> None:
        if not text:
            return
        try:
            if self._fh.tell() + len(text.encode("utf-8", "replace")) > self._max_bytes:
                self._rotate()
            self._fh.write(text)
            self._fh.flush()
        except Exception:
            # Never let logging-to-file break the server's stdout path.
            pass

    def _rotate(self) -> None:
        self._fh.close()
        # Drop the oldest, shift the rest up by one.
        oldest = self._path.with_name(self._path.name + f".{self._backups}")
        oldest.unlink(missing_ok=True)
        for i in range(self._backups - 1, 0, -1):
            src = self._path.with_name(self._path.name + f".{i}")
            if src.exists():
                src.rename(self._path.with_name(self._path.name + f".{i + 1}"))
        if self._path.exists():
            self._path.rename(self._path.with_name(self._path.name + ".1"))
        self._fh = open(self._path, "a", encoding="utf-8")

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass


class _TimestampedStream:
    """Wrap a text stream so every new line written gets a '[YYYY-MM-DD HH:MM:SS] '
    prefix. Installed over ``sys.stdout`` at server start so all server log lines
    — current and future, from any thread — are timestamped uniformly.

    Thread-safe (writes are serialized) and ``\\r``-aware, so carriage-return
    progress updates re-stamp cleanly instead of mangling the line.

    If *log_writer* is given, every stamped chunk is also mirrored to it (the
    rotating ``server.log`` file — stdout only, issue #268).
    """

    def __init__(self, stream, log_writer: "_RotatingLogWriter | None" = None) -> None:
        self._stream = stream
        self._log_writer = log_writer
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
            stamped = "".join(out)
            self._stream.write(stamped)
            if self._log_writer is not None:
                self._log_writer.write(stamped)
        return len(data)

    def flush(self) -> None:
        self._stream.flush()

    def __getattr__(self, name):
        return getattr(self._stream, name)


def _install_timestamped_stdout(log_path: Path | None = None) -> "_RotatingLogWriter | None":
    """Route server stdout through the timestamping wrapper (idempotent).

    If *log_path* is given, stdout is also mirrored to a rotating log file at
    that path; the writer is returned so the caller can close it on shutdown.
    Returns None if stdout was already wrapped or no log path was given.
    """
    if isinstance(sys.stdout, _TimestampedStream):
        return None
    log_writer = _RotatingLogWriter(log_path) if log_path is not None else None
    sys.stdout = _TimestampedStream(sys.stdout, log_writer=log_writer)
    return log_writer


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


def _auto_initialize_server(cfg: cfg_module.Config) -> cfg_module.Config:
    """Initialize the server with preset defaults — no user prompts (issue #268).

    Keeps the existing config defaults (port 8765, blank PIN = open access),
    flips ``is_server`` on, and persists. The PIN can be set afterwards via the
    GUI or by editing ``server_pin`` in ``emusync.toml``.
    """
    cfg.is_server = True
    cfg_module.save(cfg)
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

    cfg = cfg_module.load()

    # Timestamp every line the server writes to stdout (idempotent), and mirror
    # stdout to a rotating log file at ~/.emusync/server.log (issue #268).
    log_writer = _install_timestamped_stdout(Path(cfg.data_dir) / "server.log")

    # Auto-initialize with preset defaults on first start — no interactive prompt.
    if not cfg.is_server:
        cfg = _auto_initialize_server(cfg)
        click.echo(
            "EmuSync server initialized (open access — set a PIN in the GUI or "
            "emusync.toml)"
        )

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
            watch_cfg=cfg,
        )

    daemon_thread = threading.Thread(target=_start_daemon_for_server, daemon=True)
    daemon_thread.start()

    logging.getLogger("uvicorn.error").addFilter(_suppress_sse_cancel_log)

    try:
        # timeout_graceful_shutdown lets a single Ctrl+C exit cleanly: uvicorn
        # asks the long-lived SSE (/events/stream) connections to close, then
        # force-cancels them after the timeout instead of waiting forever for a
        # second Ctrl+C (issue #268).
        uvicorn.run(
            api_module.app,
            host="0.0.0.0",
            port=cfg.server_port,
            log_level="warning",
            timeout_graceful_shutdown=3,
        )
    finally:
        _daemon_shutdown.set()
        mdns_thread.join(timeout=2)
        with _mdns_lock:
            if zc and info:
                zc.unregister_service(info)
                zc.close()
        token_file.unlink(missing_ok=True)
        pid_file.unlink(missing_ok=True)
        if log_writer is not None:
            log_writer.close()


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
