"""Device listing, presence, removal, and per-device console/game-device views."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ._core import (
    _auth,
    _get_store,
    _print_activity,
    _online_devices,
    _device_names,
    _presence_lock,
)

router = APIRouter()


@router.get("/devices")
def list_devices(device_id: str = Depends(_auth)) -> list[dict]:
    with _presence_lock:
        online_set = set(_online_devices)
    return [
        {"id": d.id, "name": d.name, "last_ip": d.last_ip, "last_seen_at": d.last_seen_at, "is_online": d.id in online_set}
        for d in _get_store().list_devices()
    ]


@router.get("/whoami")
def whoami(device_id: str = Depends(_auth)) -> dict:
    return {"device_id": device_id}


@router.delete("/devices/{remove_device_id}")
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


# ── device consoles ───────────────────────────────────────────────────────────

@router.get("/devices/{target_device_id}/consoles")
def get_device_consoles(target_device_id: str, device_id: str = Depends(_auth)) -> list[dict]:
    consoles = _get_store().list_consoles(target_device_id)
    return [
        {
            "console_name": c.console_name,
            "device_game_folder": c.device_game_folder,
            "device_save_folder": c.device_save_folder,
            "device_state_folder": c.device_state_folder,
            "device_emulator": c.device_emulator,
            "device_network_folder": c.device_network_folder,
            "device_local_folder": c.device_local_folder,
        }
        for c in consoles
    ]


# ── device game-devices (any device) ─────────────────────────────────────────

@router.get("/devices/{target_device_id}/game-devices")
def get_device_game_devices(target_device_id: str, device_id: str = Depends(_auth)) -> list[dict]:
    """Return all games configured for a specific device."""
    return _get_store().list_game_devices_for_device(target_device_id)
