"""Game CRUD, the batched overview, per-game device config, and game lists."""
from __future__ import annotations

import re

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..store import GameDevice, upsert_console_for_game
from ._core import _auth, _get_store, _print_activity, _device_names

router = APIRouter()


class GameRequest(BaseModel):
    name: str
    console: str = ""
    # A manually-picked SteamGridDB game match (issue #325), shared across
    # devices. Omitted/None on a plain rename leaves the existing value alone —
    # see update_game below.
    sgdb_game_id: Optional[int] = None


class GameDeviceRequest(BaseModel):
    rom_path: str = ""
    save_path: str = ""
    launch_command: str = ""
    state_path: str = ""
    rom_folder_path: str = ""
    # Network-ROM source fields (issue #255).
    rom_source: str = "local"
    rom_rel_path: str = ""
    local_rom_path: str = ""
    rom_sha256: str = ""
    # Transient: populate the console row's per-console network/local folders.
    device_network_folder: str = ""
    device_local_folder: str = ""


@router.get("/games")
def list_games(device_id: str = Depends(_auth)) -> list[dict]:
    return [
        {"slug": g.slug, "name": g.name, "console": g.console, "sgdb_game_id": g.sgdb_game_id}
        for g in _get_store().list_games()
    ]


@router.post("/games")
def add_game(req: GameRequest, device_id: str = Depends(_auth)) -> dict:
    slug = re.sub(r"[^a-z0-9]+", "-", req.name.lower()).strip("-")
    game = _get_store().add_game(slug, req.name, req.console)
    return {"slug": game.slug, "name": game.name, "console": game.console, "sgdb_game_id": game.sgdb_game_id}


@router.get("/games/overview")
def games_overview(device_id: str = Depends(_auth)) -> list[dict]:
    """Per-device snapshot of every game (lock + last save + this device's config)
    in one response, so the GUI doesn't fan out 3 requests per game on a timer.

    Registered before /games/{slug} so "overview" isn't matched as a slug."""
    return _get_store().games_overview(device_id)


@router.get("/games/{slug}")
def get_game(slug: str, device_id: str = Depends(_auth)) -> dict:
    game = _get_store().get_game(slug)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    return {"slug": game.slug, "name": game.name, "console": game.console, "sgdb_game_id": game.sgdb_game_id}


@router.put("/games/{slug}")
def update_game(slug: str, req: GameRequest, device_id: str = Depends(_auth)) -> dict:
    store = _get_store()
    if not store.get_game(slug):
        raise HTTPException(status_code=404, detail="Game not found")
    store.update_game_name(slug, req.name)
    if req.console:
        store.update_game_console(slug, req.console)
    if req.sgdb_game_id:
        store.update_game_sgdb_id(slug, req.sgdb_game_id)
    game = store.get_game(slug)
    return {"slug": slug, "name": game.name, "console": game.console, "sgdb_game_id": game.sgdb_game_id}


@router.delete("/games/{slug}")
def delete_game(slug: str, device_id: str = Depends(_auth)) -> dict:
    if not _get_store().get_game(slug):
        raise HTTPException(status_code=404, detail="Game not found")
    _get_store().remove_game(slug)
    return {"ok": True}


# ── game_devices ──────────────────────────────────────────────────────────────

@router.get("/games/{slug}/device")
def get_game_device(slug: str, device_id: str = Depends(_auth)) -> dict:
    gd = _get_store().get_game_device(slug, device_id)
    if not gd:
        raise HTTPException(status_code=404, detail="No device config for this game")
    return {"rom_path": gd.rom_path, "save_path": gd.save_path, "launch_command": gd.launch_command,
            "state_path": gd.state_path, "rom_folder_path": gd.rom_folder_path,
            "rom_source": gd.rom_source, "rom_rel_path": gd.rom_rel_path,
            "local_rom_path": gd.local_rom_path, "rom_sha256": gd.rom_sha256}


@router.delete("/games/{slug}/device")
def remove_game_device(slug: str, device_id: str = Depends(_auth)) -> dict:
    """Unlink a game from the calling device only (issue #343) — the game
    itself, its saves/states, and every other device's config are untouched.
    Idempotent: a device with no config for this game just gets {"ok": True}."""
    if not _get_store().get_game(slug):
        raise HTTPException(status_code=404, detail="Game not found")
    _get_store().remove_game_device(slug, device_id)
    return {"ok": True}


@router.get("/games/{slug}/network-source")
def get_game_network_source(slug: str, device_id: str = Depends(_auth)) -> dict:
    """A network-drive config for this game on any device (issue #270).

    Lets a device that doesn't have the game configured locally reach the same
    shared drive: it joins the returned ``rom_rel_path`` to its own mount root.
    404 when no device has the game on a network share.
    """
    if not _get_store().get_game(slug):
        raise HTTPException(status_code=404, detail="Game not found")
    src = _get_store().get_network_source_for_game(slug)
    if not src:
        raise HTTPException(status_code=404, detail="No network-sourced config for this game")
    return src


@router.get("/games/{slug}/devices")
def list_game_devices(slug: str, device_id: str = Depends(_auth)) -> list[dict]:
    if not _get_store().get_game(slug):
        raise HTTPException(status_code=404, detail="Game not found")
    return _get_store().list_devices_for_game(slug)


@router.put("/games/{slug}/device")
def set_game_device(slug: str, req: GameDeviceRequest, device_id: str = Depends(_auth)) -> dict:
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
            rom_source=req.rom_source or "local",
            rom_rel_path=req.rom_rel_path,
            local_rom_path=req.local_rom_path,
            rom_sha256=req.rom_sha256,
        )
    )

    # Auto-configure console if game has console and paths
    if game.console and (req.rom_path or req.save_path):
        upsert_console_for_game(
            store, device_id, game.console,
            req.rom_path, req.save_path, req.rom_folder_path,
            network_folder=req.device_network_folder,
            local_folder=req.device_local_folder,
        )

    if req.rom_path:
        store.log_event("game_added", slug, device_id, rom_path=req.rom_path)
        device_name = _device_names.get(device_id, device_id)
        _print_activity(f"new {game.console} game added: {game.name} to {device_name} at the local path {req.rom_path}")
    return {"ok": True}


# ── game-devices (current device) ────────────────────────────────────────────

@router.get("/game-devices")
def list_my_game_devices(device_id: str = Depends(_auth)) -> list[dict]:
    """Return all games configured for the calling device."""
    return _get_store().list_game_devices_for_device(device_id)
