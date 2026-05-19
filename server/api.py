from __future__ import annotations

import uuid
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
_master_token: str = ""


def init(store: Store, master_token: str) -> None:
    global _store, _master_token
    _store = store
    _master_token = master_token


def _get_store() -> Store:
    if _store is None:
        raise RuntimeError("Store not initialized")
    return _store


def _auth(authorization: str = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    token = authorization.removeprefix("Bearer ")
    store = _get_store()
    device = store.device_by_token(token)
    if not device:
        raise HTTPException(status_code=401, detail="Invalid token")
    return device.id


# ── public ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


class PairRequest(BaseModel):
    master_token: str
    device_name: str
    device_id: str


@app.post("/pair")
def pair(req: PairRequest) -> dict:
    if _master_token and req.master_token != _master_token:
        raise HTTPException(status_code=403, detail="Invalid master token")
    token = str(uuid.uuid4())
    device = _get_store().register_device(req.device_id, req.device_name, token)
    return {"device_id": device.id, "token": device.token}


# ── devices ───────────────────────────────────────────────────────────────────

@app.get("/devices")
def list_devices(device_id: str = Depends(_auth)) -> list[dict]:
    return [{"id": d.id, "name": d.name} for d in _get_store().list_devices()]


# ── games ─────────────────────────────────────────────────────────────────────

class GameRequest(BaseModel):
    name: str


@app.get("/games")
def list_games(device_id: str = Depends(_auth)) -> list[dict]:
    return [{"slug": g.slug, "name": g.name} for g in _get_store().list_games()]


@app.post("/games")
def add_game(req: GameRequest, device_id: str = Depends(_auth)) -> dict:
    import re
    slug = re.sub(r"[^a-z0-9]+", "-", req.name.lower()).strip("-")
    game = _get_store().add_game(slug, req.name)
    return {"slug": game.slug, "name": game.name}


@app.get("/games/{slug}")
def get_game(slug: str, device_id: str = Depends(_auth)) -> dict:
    game = _get_store().get_game(slug)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    return {"slug": game.slug, "name": game.name}


@app.put("/games/{slug}")
def update_game(slug: str, req: GameRequest, device_id: str = Depends(_auth)) -> dict:
    if not _get_store().get_game(slug):
        raise HTTPException(status_code=404, detail="Game not found")
    _get_store().add_game(slug, req.name)
    return {"slug": slug, "name": req.name}


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


@app.get("/games/{slug}/device")
def get_game_device(slug: str, device_id: str = Depends(_auth)) -> dict:
    gd = _get_store().get_game_device(slug, device_id)
    if not gd:
        raise HTTPException(status_code=404, detail="No device config for this game")
    return {"rom_path": gd.rom_path, "save_path": gd.save_path, "launch_command": gd.launch_command}


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


# ── locks ─────────────────────────────────────────────────────────────────────

@app.post("/games/{slug}/lock")
def acquire_lock(slug: str, device_id: str = Depends(_auth)) -> dict:
    try:
        _get_store().acquire_lock(slug, device_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"ok": True}


@app.delete("/games/{slug}/lock")
def release_lock(slug: str, device_id: str = Depends(_auth)) -> dict:
    _get_store().release_lock(slug, device_id)
    return {"ok": True}


@app.get("/games/{slug}/lock")
def get_lock(slug: str, device_id: str = Depends(_auth)) -> dict:
    lock = _get_store().get_lock(slug)
    if not lock:
        return {"locked": False}
    return {"locked": True, "device_id": lock.device_id, "acquired_at": lock.acquired_at}
