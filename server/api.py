from __future__ import annotations

import threading
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .store import GameDevice, Store

app = FastAPI(title="EmuSync")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_store: Optional[Store] = None
_master_pin: str = ""
_server_device_id: str = ""
_online_devices: set[str] = set()
_device_names: dict[str, str] = {}
_presence_lock = threading.Lock()


def _monitor_presence() -> None:
    """Background thread: emit 'went offline' for idle devices every 30 seconds."""
    import time
    from datetime import datetime, timezone

    OFFLINE_TIMEOUT_SECONDS = 5 * 60
    while True:
        time.sleep(30)
        if _store is None:
            continue
        try:
            devices = _store.list_devices()
            now = datetime.now(timezone.utc)
            for d in devices:
                if d.last_seen_at is None:
                    continue
                last_seen = datetime.fromisoformat(d.last_seen_at)
                if (now - last_seen).total_seconds() > OFFLINE_TIMEOUT_SECONDS:
                    with _presence_lock:
                        if d.id in _online_devices:
                            _online_devices.discard(d.id)
                            name = _device_names.pop(d.id, d.name)
                            _print_activity(f"{name} went offline")
        except Exception:
            pass


def init(store: Store, master_pin: str, server_device_id: str = "") -> None:
    global _store, _master_pin, _server_device_id, _online_devices, _device_names
    _store = store
    _master_pin = master_pin
    _server_device_id = server_device_id
    _online_devices.clear()
    _device_names.clear()
    t = threading.Thread(target=_monitor_presence, daemon=True)
    t.start()


def _get_store() -> Store:
    if _store is None:
        raise RuntimeError("Store not initialized")
    return _store


def _print_activity(msg: str) -> None:
    print(msg, flush=True)


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
    if _master_pin and pin != _master_pin:
        raise HTTPException(status_code=401, detail="Invalid PIN")
    if not x_device_id:
        raise HTTPException(status_code=401, detail="Missing X-Device-ID header")
    store = _get_store()
    device, is_new = store.ensure_device(x_device_id, x_device_name or x_device_id)
    ip = request.client.host if request.client else "unknown"
    if request.client:
        store.touch_device(x_device_id, ip)

    with _presence_lock:
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


# ── devices ───────────────────────────────────────────────────────────────────

@app.get("/devices")
def list_devices(device_id: str = Depends(_auth)) -> list[dict]:
    return [
        {"id": d.id, "name": d.name, "last_ip": d.last_ip, "last_seen_at": d.last_seen_at}
        for d in _get_store().list_devices()
    ]


@app.get("/whoami")
def whoami(device_id: str = Depends(_auth)) -> dict:
    return {"device_id": device_id}


@app.delete("/devices/{remove_device_id}")
def remove_device(remove_device_id: str, device_id: str = Depends(_auth)) -> dict:
    store = _get_store()
    devices = store.list_devices()
    name = next((d.name for d in devices if d.id == remove_device_id), remove_device_id)
    store.log_event("device_removed", device_id=remove_device_id)
    store.remove_device(remove_device_id)
    with _presence_lock:
        _online_devices.discard(remove_device_id)
        _device_names.pop(remove_device_id, None)
    _print_activity(f"{name} unpaired")
    return {"ok": True}


# ── games ─────────────────────────────────────────────────────────────────────

class GameRequest(BaseModel):
    name: str
    console: str = ""


@app.get("/games")
def list_games(device_id: str = Depends(_auth)) -> list[dict]:
    return [{"slug": g.slug, "name": g.name, "console": g.console} for g in _get_store().list_games()]


@app.post("/games")
def add_game(req: GameRequest, device_id: str = Depends(_auth)) -> dict:
    import re
    slug = re.sub(r"[^a-z0-9]+", "-", req.name.lower()).strip("-")
    game = _get_store().add_game(slug, req.name, req.console)
    return {"slug": game.slug, "name": game.name, "console": game.console}


@app.get("/games/{slug}")
def get_game(slug: str, device_id: str = Depends(_auth)) -> dict:
    game = _get_store().get_game(slug)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    return {"slug": game.slug, "name": game.name, "console": game.console}


@app.put("/games/{slug}")
def update_game(slug: str, req: GameRequest, device_id: str = Depends(_auth)) -> dict:
    if not _get_store().get_game(slug):
        raise HTTPException(status_code=404, detail="Game not found")
    _get_store().update_game_name(slug, req.name)
    if req.console:
        _get_store().update_game_console(slug, req.console)
    game = _get_store().get_game(slug)
    return {"slug": slug, "name": game.name, "console": game.console}


@app.delete("/games/{slug}")
def delete_game(slug: str, device_id: str = Depends(_auth)) -> dict:
    if not _get_store().get_game(slug):
        raise HTTPException(status_code=404, detail="Game not found")
    _get_store().remove_game(slug)
    return {"ok": True}


# ── game_devices ──────────────────────────────────────────────────────────────

class GameDeviceRequest(BaseModel):
    rom_path: str = ""
    save_path: str = ""
    launch_command: str = ""
    state_path: str = ""
    rom_folder_path: str = ""


@app.get("/games/{slug}/device")
def get_game_device(slug: str, device_id: str = Depends(_auth)) -> dict:
    gd = _get_store().get_game_device(slug, device_id)
    if not gd:
        raise HTTPException(status_code=404, detail="No device config for this game")
    return {"rom_path": gd.rom_path, "save_path": gd.save_path, "launch_command": gd.launch_command, "state_path": gd.state_path, "rom_folder_path": gd.rom_folder_path}


@app.get("/games/{slug}/devices")
def list_game_devices(slug: str, device_id: str = Depends(_auth)) -> list[dict]:
    if not _get_store().get_game(slug):
        raise HTTPException(status_code=404, detail="Game not found")
    return _get_store().list_devices_for_game(slug)


@app.put("/games/{slug}/device")
def set_game_device(slug: str, req: GameDeviceRequest, device_id: str = Depends(_auth)) -> dict:
    import os
    import uuid
    from .store import Console

    store = _get_store()
    game = store.get_game(slug)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    store.set_game_device(
        GameDevice(
            game_slug=slug,
            device_id=device_id,
            rom_path=req.rom_path,
            save_path=req.save_path,
            launch_command=req.launch_command,
            state_path=req.state_path,
            rom_folder_path=req.rom_folder_path,
        )
    )

    # Auto-configure console if game has console and paths
    if game.console and (req.rom_path or req.save_path):
        # Extract emulator/core from save path (e.g., mGBA from /path/saves/mGBA/)
        emulator = ""
        game_folder = ""
        save_folder = ""
        state_folder = ""

        if req.save_path:
            save_dir = os.path.dirname(req.save_path)
            save_folder = save_dir
            # Try to infer emulator from save folder structure
            emulator = os.path.basename(save_dir)

        if req.rom_folder_path:
            # Use the folder path provided by GUI (the user-selected folder)
            game_folder = req.rom_folder_path
        elif req.rom_path:
            # Fall back to extracting from ROM path
            # /path/Console/GameFolder/game.rom -> /path/Console/
            rom_file_dir = os.path.dirname(req.rom_path)
            game_folder = os.path.dirname(rom_file_dir)

        if save_folder:
            # Infer state folder by replacing 'saves' with 'states'
            state_folder = save_folder.replace('saves', 'states')

        # Check if console entry with this exact ROM folder exists
        existing_consoles = store.list_consoles(device_id)
        existing_console = None
        for c in existing_consoles:
            if c.console_name == game.console and c.device_game_folder == game_folder:
                existing_console = c
                break

        if existing_console:
            # Update existing console entry for this ROM folder
            existing_console.device_save_folder = save_folder
            existing_console.device_state_folder = state_folder
            existing_console.device_emulator = emulator
            store.set_console(existing_console)
        else:
            # Create new console entry for this ROM folder
            console_obj = Console(
                id=str(uuid.uuid4()),
                device_id=device_id,
                console_name=game.console,
                shortform_name=game.console.lower()[:4],
                device_game_folder=game_folder,
                device_save_folder=save_folder,
                device_state_folder=state_folder,
                device_emulator=emulator,
            )
            store.set_console(console_obj)

    if req.rom_path:
        store.log_event("game_added", slug, device_id, rom_path=req.rom_path)
        device_name = _device_names.get(device_id, device_id)
        _print_activity(f"new {game.console} game added: {game.name} to {device_name} at the local path {req.rom_path}")
    return {"ok": True}


# ── saves ─────────────────────────────────────────────────────────────────────

@app.get("/games/{slug}/save")
def pull_save(slug: str, device_id: str = Depends(_auth)) -> Response:
    data, meta = _get_store().pull_save(slug)
    if data is None:
        return Response(status_code=204)
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={
            "X-Save-Hash": meta.hash,
            "X-Pushed-At": meta.pushed_at,
            "X-Device-Id": meta.device_id,
        },
    )


@app.post("/games/{slug}/save")
async def push_save(slug: str, request: Request, device_id: str = Depends(_auth)) -> dict:
    data = await request.body()
    meta = _get_store().push_save(slug, device_id, data)
    _get_store().log_event("save_synced", slug, device_id)
    return {"hash": meta.hash, "pushed_at": meta.pushed_at}


@app.get("/games/{slug}/save/meta")
def get_save_meta(slug: str, device_id: str = Depends(_auth)) -> Response:
    meta = _get_store().get_save_meta(slug)
    if not meta:
        return Response(status_code=204)
    return Response(
        content=f'{{"hash":"{meta.hash}","pushed_at":"{meta.pushed_at}","device_id":"{meta.device_id}"}}',
        media_type="application/json",
    )


# ── states ────────────────────────────────────────────────────────────────────

@app.get("/games/{slug}/state")
def pull_state(slug: str, device_id: str = Depends(_auth)) -> Response:
    data, meta = _get_store().pull_state(slug)
    if data is None:
        return Response(status_code=204)
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={
            "X-State-Hash": meta.hash,
            "X-Pushed-At": meta.pushed_at,
            "X-Device-Id": meta.device_id,
        },
    )


@app.post("/games/{slug}/state")
async def push_state(slug: str, request: Request, device_id: str = Depends(_auth)) -> dict:
    data = await request.body()
    meta = _get_store().push_state(slug, device_id, data)
    _get_store().log_event("state_synced", slug, device_id)
    return {"hash": meta.hash, "pushed_at": meta.pushed_at}


@app.get("/games/{slug}/state/meta")
def get_state_meta(slug: str, device_id: str = Depends(_auth)) -> Response:
    meta = _get_store().get_state_meta(slug)
    if not meta:
        return Response(status_code=204)
    return Response(
        content=f'{{"hash":"{meta.hash}","pushed_at":"{meta.pushed_at}","device_id":"{meta.device_id}"}}',
        media_type="application/json",
    )


# ── locks ─────────────────────────────────────────────────────────────────────

@app.post("/games/{slug}/lock")
def acquire_lock(slug: str, device_id: str = Depends(_auth)) -> dict:
    try:
        _get_store().acquire_lock(slug, device_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    _get_store().log_event("game_started", slug, device_id)
    return {"ok": True}


@app.delete("/games/{slug}/lock")
def release_lock(slug: str, device_id: str = Depends(_auth)) -> dict:
    _get_store().release_lock(slug, device_id)
    _get_store().log_event("game_stopped", slug, device_id)
    return {"ok": True}


@app.get("/events")
def list_events(device_id: str = Depends(_auth)) -> list:
    return _get_store().list_events()


@app.get("/games/{slug}/lock")
def get_lock(slug: str, device_id: str = Depends(_auth)) -> dict:
    lock = _get_store().get_lock(slug)
    if not lock:
        return {"locked": False}
    return {"locked": True, "device_id": lock.device_id, "acquired_at": lock.acquired_at}


# ── ROMs ──────────────────────────────────────────────────────────────────────

@app.get("/games/{slug}/rom")
def pull_rom(slug: str, device_id: str = Depends(_auth)) -> Response:
    from pathlib import Path
    store = _get_store()
    gd = store.get_game_device(slug, _server_device_id)
    if not gd or not gd.rom_path:
        raise HTTPException(status_code=404, detail="ROM not configured for this device")
    rom_path = Path(gd.rom_path)
    if not rom_path.exists():
        raise HTTPException(status_code=404, detail="ROM file not found on this device")
    return Response(
        content=rom_path.read_bytes(),
        media_type="application/octet-stream",
        headers={
            "Content-Length": str(rom_path.stat().st_size),
            "X-Rom-Filename": rom_path.name,
        },
    )


@app.post("/games/{slug}/rom")
async def push_rom(slug: str, request: Request, device_id: str = Depends(_auth)) -> dict:
    import os
    import uuid
    from pathlib import Path
    from .store import Console

    data = await request.body()
    filename = request.headers.get("X-Rom-Filename", f"{slug}.rom")
    dest_folder = request.headers.get("X-Dest-Folder", "")

    store = _get_store()
    game = store.get_game(slug)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    # Determine destination folder
    save_folder = ""
    if dest_folder:
        save_folder = dest_folder
    else:
        # Try to find console config for this game
        consoles = store.list_consoles(device_id)
        for c in consoles:
            if c.console_name == game.console:
                save_folder = c.device_game_folder
                break

    if not save_folder:
        raise HTTPException(status_code=422, detail=f"Console '{game.console}' not configured on this device")

    # Save ROM file
    rom_path = Path(save_folder) / filename
    rom_path.parent.mkdir(parents=True, exist_ok=True)
    rom_path.write_bytes(data)

    # Register game config
    store.set_game_device(
        GameDevice(
            game_slug=slug,
            device_id=device_id,
            rom_path=str(rom_path),
            save_path="",
            launch_command="",
            state_path="",
            rom_folder_path=save_folder,
        )
    )

    return {"saved_to": str(rom_path), "rom_path": str(rom_path)}


