from __future__ import annotations

import sys
import uuid
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .store import Game, GameDevice, Store

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


def _log_game_import(game: Game) -> None:
    """Log imported game details to stdout."""
    print(
        f"[IMPORT] game={game.game!r} device_id={game.device_id!r} name={game.name!r} "
        f"console={game.console!r} rom_path={game.rom_path!r} save_path={game.save_path!r} "
        f"launch_command={game.launch_command!r} state_path={game.state_path!r} "
        f"rom_folder_path={game.rom_folder_path!r}",
        file=sys.stdout,
        flush=True,
    )


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


@app.get("/whoami")
def whoami(device_id: str = Depends(_auth)) -> dict:
    return {"device_id": device_id}


@app.delete("/devices/{remove_device_id}")
def remove_device(remove_device_id: str, device_id: str = Depends(_auth)) -> dict:
    _get_store().remove_device(remove_device_id)
    return {"ok": True}


# ── games ─────────────────────────────────────────────────────────────────────

class GameRequest(BaseModel):
    name: str
    console: str = ""
    rom_path: str = ""
    save_path: str = ""
    launch_command: str = ""
    state_path: str = ""
    rom_folder_path: str = ""


class GameDeviceRequest(BaseModel):
    rom_path: str = ""
    save_path: str = ""
    launch_command: str = ""
    state_path: str = ""
    rom_folder_path: str = ""


@app.get("/games")
def list_games(device_id: str = Depends(_auth)) -> list[dict]:
    games = _get_store().list_games(device_id)
    return [
        {
            "game": g.game,
            "name": g.name,
            "console": g.console,
            "rom_path": g.rom_path,
            "save_path": g.save_path,
            "launch_command": g.launch_command,
            "state_path": g.state_path,
            "rom_folder_path": g.rom_folder_path,
            "sync_state": g.sync_state,
            "enabled": g.enabled,
        }
        for g in games
    ]


@app.post("/games")
def add_game(req: GameRequest, device_id: str = Depends(_auth)) -> dict:
    import re
    from datetime import datetime, timezone
    game_id = re.sub(r"[^a-z0-9]+", "-", req.name.lower()).strip("-")
    now = datetime.now(timezone.utc).isoformat()
    game = _get_store().add_game(
        Game(
            game=game_id,
            device_id=device_id,
            name=req.name,
            console=req.console,
            rom_path=req.rom_path,
            save_path=req.save_path,
            launch_command=req.launch_command,
            state_path=req.state_path,
            rom_folder_path=req.rom_folder_path,
            added_at=now,
        )
    )
    _log_game_import(game)
    return {
        "game": game.game,
        "name": game.name,
        "console": game.console,
        "rom_path": game.rom_path,
        "save_path": game.save_path,
        "launch_command": game.launch_command,
        "state_path": game.state_path,
        "rom_folder_path": game.rom_folder_path,
    }


@app.get("/games/{game}")
def get_game(game: str, device_id: str = Depends(_auth)) -> dict:
    g = _get_store().get_game(game, device_id)
    if not g:
        raise HTTPException(status_code=404, detail="Game not found")
    return {
        "game": g.game,
        "name": g.name,
        "console": g.console,
        "rom_path": g.rom_path,
        "save_path": g.save_path,
        "launch_command": g.launch_command,
        "state_path": g.state_path,
        "rom_folder_path": g.rom_folder_path,
        "sync_state": g.sync_state,
        "enabled": g.enabled,
    }


@app.put("/games/{game}")
def update_game(game: str, req: GameRequest, device_id: str = Depends(_auth)) -> dict:
    if not _get_store().get_game(game, device_id):
        raise HTTPException(status_code=404, detail="Game not found")
    existing = _get_store().get_game(game, device_id)
    updated = Game(
        game=game,
        device_id=device_id,
        name=req.name if req.name else existing.name,
        console=req.console if req.console else existing.console,
        rom_path=req.rom_path if req.rom_path else existing.rom_path,
        save_path=req.save_path if req.save_path else existing.save_path,
        launch_command=req.launch_command if req.launch_command else existing.launch_command,
        state_path=req.state_path if req.state_path else existing.state_path,
        rom_folder_path=req.rom_folder_path if req.rom_folder_path else existing.rom_folder_path,
        added_at=existing.added_at,
        enabled=existing.enabled,
    )
    _get_store().add_game(updated)
    return {
        "game": updated.game,
        "name": updated.name,
        "console": updated.console,
        "rom_path": updated.rom_path,
        "save_path": updated.save_path,
        "launch_command": updated.launch_command,
        "state_path": updated.state_path,
        "rom_folder_path": updated.rom_folder_path,
    }


@app.delete("/games/{game}")
def delete_game(game: str, device_id: str = Depends(_auth)) -> dict:
    if not _get_store().get_game(game, device_id):
        raise HTTPException(status_code=404, detail="Game not found")
    _get_store().remove_game(game, device_id)
    return {"ok": True}


# ── game_devices ──────────────────────────────────────────────────────────────
# Note: These endpoints are kept for backwards compatibility but are no longer the primary way to configure games
# Game config is now stored directly on the games table

@app.get("/games/{game}/device")
def get_game_device(game: str, device_id: str = Depends(_auth)) -> dict:
    g = _get_store().get_game(game, device_id)
    if not g:
        raise HTTPException(status_code=404, detail="Game not found")
    return {
        "rom_path": g.rom_path,
        "save_path": g.save_path,
        "launch_command": g.launch_command,
        "state_path": g.state_path,
        "rom_folder_path": g.rom_folder_path,
    }


@app.put("/games/{game}/device")
def set_game_device(game: str, req: GameDeviceRequest, device_id: str = Depends(_auth)) -> dict:
    g = _get_store().get_game(game, device_id)
    if not g:
        raise HTTPException(status_code=404, detail="Game not found")
    updated = Game(
        game=game,
        device_id=device_id,
        name=g.name,
        console=g.console,
        rom_path=req.rom_path,
        save_path=req.save_path,
        launch_command=req.launch_command,
        state_path=req.state_path,
        rom_folder_path=req.rom_folder_path,
        added_at=g.added_at,
        enabled=g.enabled,
    )
    _get_store().add_game(updated)
    return {"ok": True}


# ── saves ─────────────────────────────────────────────────────────────────────

@app.get("/games/{game}/save")
def pull_save(game: str, device_id: str = Depends(_auth)) -> Response:
    data, meta = _get_store().pull_save(game)
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


@app.post("/games/{game}/save")
async def push_save(game: str, request: Request, device_id: str = Depends(_auth)) -> dict:
    data = await request.body()
    meta = _get_store().push_save(game, device_id, data)
    _get_store().log_event("save_synced", game, device_id)
    return {"hash": meta.hash, "pushed_at": meta.pushed_at}


@app.get("/games/{game}/save/meta")
def get_save_meta(game: str, device_id: str = Depends(_auth)) -> Response:
    meta = _get_store().get_save_meta(game)
    if not meta:
        return Response(status_code=204)
    return Response(
        content=f'{{"hash":"{meta.hash}","pushed_at":"{meta.pushed_at}","device_id":"{meta.device_id}"}}',
        media_type="application/json",
    )


# ── states ────────────────────────────────────────────────────────────────────

@app.get("/games/{game}/state")
def pull_state(game: str, device_id: str = Depends(_auth)) -> Response:
    data, meta = _get_store().pull_state(game)
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


@app.post("/games/{game}/state")
async def push_state(game: str, request: Request, device_id: str = Depends(_auth)) -> dict:
    data = await request.body()
    meta = _get_store().push_state(game, device_id, data)
    _get_store().log_event("state_synced", game, device_id)
    return {"hash": meta.hash, "pushed_at": meta.pushed_at}


@app.get("/games/{game}/state/meta")
def get_state_meta(game: str, device_id: str = Depends(_auth)) -> Response:
    meta = _get_store().get_state_meta(game)
    if not meta:
        return Response(status_code=204)
    return Response(
        content=f'{{"hash":"{meta.hash}","pushed_at":"{meta.pushed_at}","device_id":"{meta.device_id}"}}',
        media_type="application/json",
    )


# ── locks ─────────────────────────────────────────────────────────────────────

@app.post("/games/{game}/lock")
def acquire_lock(game: str, device_id: str = Depends(_auth)) -> dict:
    try:
        _get_store().acquire_lock(game, device_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    _get_store().log_event("game_started", game, device_id)
    return {"ok": True}


@app.delete("/games/{game}/lock")
def release_lock(game: str, device_id: str = Depends(_auth)) -> dict:
    _get_store().release_lock(game, device_id)
    _get_store().log_event("game_stopped", game, device_id)
    return {"ok": True}


@app.get("/events")
def list_events(device_id: str = Depends(_auth)) -> list:
    return _get_store().list_events()


@app.get("/games/{game}/lock")
def get_lock(game: str, device_id: str = Depends(_auth)) -> dict:
    lock = _get_store().get_lock(game)
    if not lock:
        return {"locked": False}
    return {"locked": True, "device_id": lock.device_id, "acquired_at": lock.acquired_at}


@app.post("/games/{game}/push-saves")
def push_saves(game: str, device_id: str = Depends(_auth)) -> dict:
  """Manually trigger a push of the game's save and state files to the server."""
  from pathlib import Path

  g = _get_store().get_game(game, device_id)
  if not g:
    raise HTTPException(status_code=404, detail="Game not found")

  pushed = {"save": False, "state": False}

  # Push save if it exists
  if g.save_path:
    save_path = Path(g.save_path)
    if save_path.exists():
      data = save_path.read_bytes()
      meta = _get_store().push_save(game, device_id, data)
      _get_store().log_event("save_synced", game, device_id)
      pushed["save"] = True

  # Push state if configured and exists
  if g.state_path:
    state_path = Path(g.state_path)
    if state_path.exists():
      data = state_path.read_bytes()
      meta = _get_store().push_state(game, device_id, data)
      _get_store().log_event("state_synced", game, device_id)
      pushed["state"] = True

  return {"ok": True, "pushed": pushed}
