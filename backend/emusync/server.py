import uuid
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from . import config as cfg_module
from . import mdns_service
from .store import GameDevice, Store

_store: Optional[Store] = None
_master_token: Optional[str] = None
_mdns_stop = None

security = HTTPBearer(auto_error=False)
app = FastAPI(title="EmuSync")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_store() -> Store:
    assert _store is not None
    return _store


def _auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Store = Depends(_get_store),
):
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing token")
    device = db.device_by_token(credentials.credentials)
    if not device:
        raise HTTPException(status_code=401, detail="Invalid token")
    return device


# ── Setup / public ─────────────────────────────────────────────────────────


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/setup-state")
def setup_state():
    cfg = cfg_module.load()
    return {
        "configured": bool(cfg.token),
        "is_server": cfg.is_server,
        "device_name": cfg.device_name,
        "device_id": cfg.device_id,
        "server_host": cfg.server_host,
        "server_port": cfg.server_port,
    }


@app.post("/setup/init-server")
def setup_init_server():
    cfg = cfg_module.load()
    cfg.is_server = True
    cfg_module.save(cfg)
    return {"master_token": _master_token}


class DiscoverResponse(BaseModel):
    name: str
    host: str
    port: int


@app.get("/setup/discover")
def setup_discover():
    results = mdns_service.discover(5.0)
    return [{"name": r.name, "host": r.host, "port": r.port} for r in results]


# ── Pairing ────────────────────────────────────────────────────────────────


class PairRequest(BaseModel):
    master_token: str
    device_name: str
    device_id: str


@app.post("/pair")
def pair(req: PairRequest, db: Store = Depends(_get_store)):
    if req.master_token != _master_token:
        raise HTTPException(status_code=401, detail="Invalid master token")
    token = str(uuid.uuid4())
    db.register_device(req.device_id, req.device_name, token)
    return {"device_id": req.device_id, "token": token}


# ── Devices ────────────────────────────────────────────────────────────────


@app.get("/devices")
def list_devices(device=Depends(_auth), db: Store = Depends(_get_store)):
    return db.list_devices()


# ── Games ──────────────────────────────────────────────────────────────────


class GameCreate(BaseModel):
    slug: str
    name: str


class GameUpdate(BaseModel):
    name: Optional[str] = None


@app.get("/games")
def list_games(device=Depends(_auth), db: Store = Depends(_get_store)):
    return db.list_games()


@app.post("/games", status_code=201)
def add_game(req: GameCreate, device=Depends(_auth), db: Store = Depends(_get_store)):
    return db.add_game(req.slug, req.name)


@app.get("/games/{slug}")
def get_game(slug: str, device=Depends(_auth), db: Store = Depends(_get_store)):
    g = db.get_game(slug)
    if not g:
        raise HTTPException(status_code=404, detail="Game not found")
    return g


@app.put("/games/{slug}")
def update_game(slug: str, req: GameUpdate, device=Depends(_auth), db: Store = Depends(_get_store)):
    g = db.get_game(slug)
    if not g:
        raise HTTPException(status_code=404, detail="Game not found")
    if req.name:
        db.update_game_name(slug, req.name)
    return db.get_game(slug)


@app.delete("/games/{slug}", status_code=204)
def remove_game(slug: str, device=Depends(_auth), db: Store = Depends(_get_store)):
    if not db.get_game(slug):
        raise HTTPException(status_code=404, detail="Game not found")
    db.remove_game(slug)


# ── Game-device config ─────────────────────────────────────────────────────


class GameDeviceConfig(BaseModel):
    rom_path: Optional[str] = ""
    save_path: Optional[str] = ""
    launch_command: Optional[str] = ""


@app.get("/games/{slug}/device")
def get_game_device(slug: str, device=Depends(_auth), db: Store = Depends(_get_store)):
    gd = db.get_game_device(slug, device.id)
    if not gd:
        raise HTTPException(status_code=404, detail="Not configured for this device")
    return gd


@app.put("/games/{slug}/device")
def set_game_device(
    slug: str, req: GameDeviceConfig, device=Depends(_auth), db: Store = Depends(_get_store)
):
    gd = GameDevice(
        game_slug=slug,
        device_id=device.id,
        rom_path=req.rom_path or "",
        save_path=req.save_path or "",
        launch_command=req.launch_command or "",
    )
    db.set_game_device(gd)
    return db.get_game_device(slug, device.id)


# ── Saves ──────────────────────────────────────────────────────────────────


@app.get("/games/{slug}/save")
def pull_save(slug: str, device=Depends(_auth), db: Store = Depends(_get_store)):
    data, meta = db.pull_save(slug)
    if data is None:
        return Response(status_code=204)
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"X-Save-SHA256": meta.sha256, "X-Save-Size": str(meta.size)},
    )


@app.post("/games/{slug}/save")
async def push_save(slug: str, request: Request, device=Depends(_auth), db: Store = Depends(_get_store)):
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="No save data provided")
    meta = db.push_save(slug, device.id, data)
    return {"sha256": meta.sha256, "size": meta.size, "created_at": meta.created_at}


@app.get("/games/{slug}/save/meta")
def get_save_meta(slug: str, device=Depends(_auth), db: Store = Depends(_get_store)):
    meta = db.get_save_meta(slug)
    if not meta:
        return Response(status_code=204)
    return meta


# ── Locks ──────────────────────────────────────────────────────────────────


@app.post("/games/{slug}/lock")
def acquire_lock(slug: str, device=Depends(_auth), db: Store = Depends(_get_store)):
    try:
        db.acquire_lock(slug, device.id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"locked": True}


@app.delete("/games/{slug}/lock")
def release_lock(slug: str, device=Depends(_auth), db: Store = Depends(_get_store)):
    db.release_lock(slug, device.id)
    return {"released": True}


@app.get("/games/{slug}/lock")
def get_lock(slug: str, device=Depends(_auth), db: Store = Depends(_get_store)):
    lock = db.get_lock(slug)
    if not lock:
        return {"locked": False}
    return {"locked": True, "device_id": lock.device_id, "acquired_at": lock.acquired_at}


# ── Factory ────────────────────────────────────────────────────────────────


def create_app(db: Store, token: str) -> FastAPI:
    global _store, _master_token
    _store = db
    _master_token = token
    return app
