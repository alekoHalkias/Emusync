from __future__ import annotations

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


def init(store: Store, master_pin: str) -> None:
    global _store, _master_pin
    _store = store
    _master_pin = master_pin


def _get_store() -> Store:
    if _store is None:
        raise RuntimeError("Store not initialized")
    return _store


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
    store.ensure_device(x_device_id, x_device_name or x_device_id)
    if request.client:
        store.touch_device(x_device_id, request.client.host)
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
    _get_store().remove_device(remove_device_id)
    return {"ok": True}


# ── consoles ──────────────────────────────────────────────────────────────────

@app.get("/consoles")
def list_consoles(device_id: str = Depends(_auth)) -> list[dict]:
    return [
        {
            "id": c.id,
            "console_name": c.console_name,
            "shortform_name": c.shortform_name,
            "device_save_folder": c.device_save_folder,
            "device_state_folder": c.device_state_folder,
            "device_game_folder": c.device_game_folder,
        }
        for c in _get_store().list_consoles(device_id)
    ]


# ── games ─────────────────────────────────────────────────────────────────────

class GameRequest(BaseModel):
    name: str
    console: str = ""
    rom_path: str = ""
    save_path: str = ""
    launch_command: str = ""
    state_path: str = ""
    rom_folder_path: str = ""


@app.get("/games")
def list_games(device_id: str = Depends(_auth)) -> list[dict]:
    return [{"slug": g.slug, "name": g.name, "console": g.console} for g in _get_store().list_games()]


@app.post("/games")
def add_game(req: GameRequest, device_id: str = Depends(_auth)) -> dict:
    import re
    slug = re.sub(r"[^a-z0-9]+", "-", req.name.lower()).strip("-")
    game = _get_store().add_game(slug, req.name, req.console)

    # If device paths are provided, store them immediately
    if req.rom_path or req.save_path or req.launch_command or req.state_path:
        _get_store().set_game_device(
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
def get_game_device(slug: str, for_device: str | None = None, device_id: str = Depends(_auth)) -> dict:
    # Allow querying another device's config (for remote pulls)
    query_device_id = for_device or device_id
    gd = _get_store().get_game_device(slug, query_device_id)
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
    if not _get_store().get_game(slug):
        raise HTTPException(status_code=404, detail="Game not found")
    _get_store().set_game_device(
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


# ── roms ──────────────────────────────────────────────────────────────────────

@app.get("/games/{slug}/rom")
def pull_rom(slug: str, device_id: str = Depends(_auth)) -> Response:
    data, meta = _get_store().pull_rom(slug)
    if data is None:
        return Response(status_code=204)
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={
            "X-ROM-Hash": meta.hash,
            "X-Pushed-At": meta.pushed_at,
            "X-Device-Id": meta.device_id,
        },
    )


@app.post("/games/{slug}/rom")
async def push_rom(slug: str, request: Request, device_id: str = Depends(_auth)) -> dict:
    data = await request.body()
    filename = request.headers.get("X-ROM-Filename", f"{slug}.rom")
    rom_dir = _get_store()._data_dir / "roms"
    rom_dir.mkdir(parents=True, exist_ok=True)
    rom_path = rom_dir / filename
    rom_path.write_bytes(data)
    meta = _get_store().push_rom(slug, device_id, data, filename)
    _get_store().log_event("rom_synced", slug, device_id)
    return {"hash": meta.hash, "pushed_at": meta.pushed_at}


@app.get("/games/{slug}/rom/meta")
def get_rom_meta(slug: str, device_id: str = Depends(_auth)) -> Response:
    meta = _get_store().get_rom_meta(slug)
    if not meta:
        return Response(status_code=204)
    return Response(
        content=f'{{"hash":"{meta.hash}","pushed_at":"{meta.pushed_at}","device_id":"{meta.device_id}"}}',
        media_type="application/json",
    )


# ── file serving (direct device-to-device transfers) ─────────────────────────

@app.get("/file")
def serve_file(path: str, device_id: str = Depends(_auth)) -> Response:
    """Serve a file from disk by path. Used for direct device-to-device transfers."""
    from pathlib import Path as PathlibPath
    import hashlib

    file_path = PathlibPath(path).expanduser()

    # Security: prevent directory traversal
    if ".." in str(file_path):
        raise HTTPException(status_code=403, detail="Path traversal not allowed")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    if not file_path.is_file():
        raise HTTPException(status_code=403, detail="Not a file")

    try:
        data = file_path.read_bytes()
        file_hash = hashlib.sha256(data).hexdigest()
        return Response(
            content=data,
            media_type="application/octet-stream",
            headers={
                "X-File-Hash": file_hash,
                "X-File-Size": str(len(data)),
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(exc)}")


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


