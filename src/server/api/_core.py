"""Core of the FastAPI app: the app object, shared mutable state, the `_auth`
dependency, activity logging, ROM-staging helpers, and `init()`.

The route handlers live in sibling modules as APIRouters and are wired onto
`app` in this package's __init__. They reach shared state through the accessors
here (`_get_store()`, `get_data_dir()`) and the live presence objects, never by
re-importing the reassigned globals directly.
"""
from __future__ import annotations

import hmac
import logging
import shutil
import sys
import threading
from pathlib import Path
from typing import Optional

import asyncio

logger = logging.getLogger("emusync.api")

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from ..store import Store

app = FastAPI(title="EmuSync")

app.add_middleware(
    CORSMiddleware,
    # Electron renderer (file:// -> Origin "null") and the local dev server only (#692).
    allow_origin_regex=r"null|https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)

_store: Optional[Store] = None
_master_pin: str = ""
_data_dir: str = ""
_online_devices: set[str] = set()
_device_names: dict[str, str] = {}
_presence_lock = threading.Lock()
_device_event_queues: dict[str, "asyncio.Queue"] = {}
_monitor_started: bool = False
# At-rest snapshot of save/state integrity, refreshed on startup and on demand
# (issue #285): {slug: {"save": <verdict>, "state": <verdict>}}.
_integrity_status: dict[str, dict] = {}

# A device with no request in this long is declared offline (and any lock it
# holds force-released, issue #238). Module-level so cli/run.py's lock-heartbeat
# can size its own interval safely under it — see that module for why the two
# must stay in sync (issue #458 follow-up: a headless "emusync run" session,
# e.g. Steam Deck Gaming Mode with no GUI /whoami heartbeat, has nothing else
# touching presence, so its own heartbeat cadence IS the only signal keeping it
# "online" for the whole play session).
OFFLINE_TIMEOUT_SECONDS = 5 * 60


def _presence_tick() -> None:
    """One monitor pass: declare idle devices offline and release their locks.

    Each device is handled on its own so one bad row can't stop the rest, and
    `_presence_lock` only guards the in-memory sets, never DB work (#704)."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    for d in _store.list_devices():
        if d.last_seen_at is None:
            continue
        try:
            last_seen = datetime.fromisoformat(d.last_seen_at)
            if last_seen.tzinfo is None:  # naive stamp: treat as UTC
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            if (now - last_seen).total_seconds() <= OFFLINE_TIMEOUT_SECONDS:
                continue
            with _presence_lock:
                if d.id not in _online_devices:
                    continue
                _online_devices.discard(d.id)
                name = _device_names.pop(d.id, d.name)
            _print_activity(f"{name} went offline")
            # Release any locks the now-offline device still holds so a
            # crashed device doesn't block a game until the TTL (issue #238).
            for slug in _store.release_device_locks(d.id):
                _store.log_event("game_stopped", slug, d.id)
                _print_activity(f"{_game_label(slug)} lock released ({name} went offline)")
        except Exception:
            logger.exception("presence monitor failed for device %s", d.id)


def _monitor_presence() -> None:
    """Background thread: emit 'went offline' for idle devices every 30 seconds."""
    import time

    while True:
        time.sleep(30)
        if _store is None:
            continue
        try:
            _presence_tick()
        except Exception:
            # Never let a transient failure kill the monitor thread silently —
            # log it (with traceback) and keep polling (issue #241).
            logger.exception("presence monitor iteration failed")


def init(store: Store, master_pin: str, data_dir: str = "") -> None:
    global _store, _master_pin, _data_dir, _online_devices, _device_names, _monitor_started
    _store = store
    _master_pin = master_pin
    _data_dir = data_dir
    _online_devices.clear()
    _device_names.clear()
    _sweep_stale_staging()
    _run_integrity_sweep()
    if not _monitor_started:
        _monitor_started = True
        t = threading.Thread(target=_monitor_presence, daemon=True)
        t.start()


def get_data_dir() -> str:
    """Live accessor for the configured data dir (reassigned by init())."""
    return _data_dir


def _staging_root() -> Optional[Path]:
    return Path(_data_dir) / "rom_staging" if _data_dir else None


def _remove_staging_dir(staged_file: str) -> None:
    """Delete the per-transfer staging directory once a transfer is finished.

    Each transfer stages its file under `rom_staging/{transfer_id}/{filename}`,
    so removing the file's parent reclaims the whole transfer's disk. Guarded so
    it only ever deletes directories directly under the staging root.
    """
    if not staged_file:
        return
    subdir = Path(staged_file).parent
    root = _staging_root()
    if root is not None and subdir.parent == root and subdir.exists():
        shutil.rmtree(subdir, ignore_errors=True)


def _sweep_stale_staging() -> None:
    """On startup, drop staging dirs whose transfer is gone or already finished."""
    root = _staging_root()
    if root is None or not root.exists() or _store is None:
        return
    for sub in root.iterdir():
        if not sub.is_dir():
            continue
        transfer = _store.get_rom_transfer(sub.name)
        if transfer is None or transfer.status != "pending":
            shutil.rmtree(sub, ignore_errors=True)
        elif _is_stale(transfer.queued_at):
            # Never fetched: reclaim the disk and stop offering it (#701).
            _store.update_transfer_status(transfer.id, "failed")
            shutil.rmtree(sub, ignore_errors=True)


# ponytail: fixed age, make it a Config field if users hit it
_STAGING_MAX_AGE_DAYS = 7


def _is_stale(queued_at: str) -> bool:
    from datetime import datetime, timedelta, timezone
    try:
        return datetime.fromisoformat(queued_at) < datetime.now(timezone.utc) - timedelta(days=_STAGING_MAX_AGE_DAYS)
    except ValueError:
        return False


def _get_store() -> Store:
    if _store is None:
        raise RuntimeError("Store not initialized")
    return _store


def _run_integrity_sweep() -> None:
    """Recompute the integrity snapshot and log any damaged current blobs.

    Runs once on startup and on demand (manual rescan). No per-request or timer
    cost — the per-game endpoint recomputes a single game when freshness matters
    (e.g. right after a restore). See issue #285.
    """
    global _integrity_status
    if _store is None:
        return
    _integrity_status = _store.sweep_integrity()
    for slug, kinds in _integrity_status.items():
        for kind, verdict in kinds.items():
            if verdict["status"] == "damaged":
                _print_activity(
                    f"⚠ integrity: {kind} for {_game_label(slug)} looks damaged "
                    f"({', '.join(verdict['reasons'])})"
                )


def get_integrity_status() -> dict:
    """Live accessor for the at-rest integrity snapshot (issue #285)."""
    return _integrity_status


def _print_activity(msg: str) -> None:
    # Single write so concurrent worker threads can't interleave a line (the
    # timestamp wrapper over stdout serializes a whole write() call atomically).
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()


def _device_label(device_id: str) -> str:
    """Human-readable device name for log lines (falls back to the id)."""
    with _presence_lock:
        name = _device_names.get(device_id)
    if name:
        return name
    if _store is not None:
        for dev in _store.list_devices():
            if dev.id == device_id:
                return dev.name
    return device_id


def _game_label(slug: str) -> str:
    """Human-readable game name for log lines (falls back to the slug)."""
    if _store is not None:
        game = _store.get_game(slug)
        if game:
            return game.name
    return slug


def _safe_segment(value: str, what: str) -> str:
    """Reject values unsafe to use as a single path segment (400)."""
    if (not value or value in (".", "..") or len(value) > 255
            or any(c in "/\\" or not c.isprintable() for c in value)):
        raise HTTPException(status_code=400, detail=f"Invalid {what}")
    return value


def _clean_header(value: Optional[str]) -> str:
    """Strip control characters (log forging) and cap length."""
    return "".join(c for c in (value or "") if c.isprintable()).strip()[:64]


def _auth(
    request: Request,
    authorization: str = Header(None),
    x_device_id: str = Header(None),
    x_device_name: str = Header(None),
) -> str:
    """Authenticate with PIN + device identity headers.

    Authorization: Bearer <server_pin>   (empty string for open servers)
    X-Device-ID:   <device_uuid>         (required)
    X-Device-Name: <display_name>        (optional — used on first auto-register)

    The device is auto-registered on first request; no explicit /pair step needed.
    """
    pin = (authorization or "").removeprefix("Bearer ")
    if _master_pin and not hmac.compare_digest(pin.encode(), _master_pin.encode()):
        raise HTTPException(status_code=401, detail="Invalid PIN")
    x_device_id = _clean_header(x_device_id)
    if not x_device_id:
        raise HTTPException(status_code=401, detail="Missing X-Device-ID header")
    store = _get_store()
    device, is_new = store.ensure_device(x_device_id, _clean_header(x_device_name) or x_device_id)
    ip = request.client.host if request.client else "unknown"
    merged: list[str] = []
    if request.client:
        merged = store.touch_device(x_device_id, ip)

    with _presence_lock:
        for old in merged:  # same machine under an older UUID (#656)
            _online_devices.discard(old)
            _device_names.pop(old, None)
        if merged:
            _print_activity(f"{device.name} re-paired, merged {len(merged)} duplicate device(s)")
        if is_new:
            _print_activity(f"new device paired called {device.name} at ip:{ip}")
        elif x_device_id not in _online_devices:
            _print_activity(f"{device.name} online")
        _online_devices.add(x_device_id)
        _device_names[x_device_id] = device.name

    return x_device_id


# ── public ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
