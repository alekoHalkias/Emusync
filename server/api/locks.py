"""Game locks (run/stop) and the activity event log."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ._core import _auth, _get_store, _print_activity, _device_label, _game_label

router = APIRouter()


@router.post("/games/{slug}/lock")
def acquire_lock(slug: str, device_id: str = Depends(_auth)) -> dict:
    try:
        _get_store().acquire_lock(slug, device_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    _get_store().log_event("game_started", slug, device_id)
    _print_activity(f"{_game_label(slug)} is running on {_device_label(device_id)}")
    return {"ok": True}


@router.delete("/games/{slug}/lock")
def release_lock(slug: str, device_id: str = Depends(_auth)) -> dict:
    _get_store().release_lock(slug, device_id)
    _get_store().log_event("game_stopped", slug, device_id)
    _print_activity(f"{_game_label(slug)} stopped on {_device_label(device_id)}")
    return {"ok": True}


@router.get("/events")
def list_events(device_id: str = Depends(_auth)) -> list:
    return _get_store().list_events()


@router.get("/games/{slug}/lock")
def get_lock(slug: str, device_id: str = Depends(_auth)) -> dict:
    lock = _get_store().get_lock(slug)
    if not lock:
        return {"locked": False}
    return {"locked": True, "device_id": lock.device_id, "acquired_at": lock.acquired_at}
