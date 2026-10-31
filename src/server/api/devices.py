"""Device listing, presence, removal, and per-device console/game-device views."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

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
            "id": c.id,
            "console_name": c.console_name,
            "device_game_folder": c.device_game_folder,
            "device_save_folder": c.device_save_folder,
            "device_state_folder": c.device_state_folder,
            "device_emulator": c.device_emulator,
            "device_network_folder": c.device_network_folder,
            "device_local_folder": c.device_local_folder,
            "device_extra_folders": c.device_extra_folders,
            "import_is_network": c.import_is_network,
            "import_remote_path": c.import_remote_path,
        }
        for c in consoles
    ]


class ConsoleFoldersRequest(BaseModel):
    device_game_folder: str = ""
    device_save_folder: str = ""
    device_state_folder: str = ""
    device_emulator: str = ""
    device_network_folder: str = ""
    device_local_folder: str = ""
    device_extra_folders: Optional[list[str]] = None
    import_is_network: bool = False
    import_remote_path: str = ""


@router.put("/devices/{target_device_id}/consoles/{console_id}")
def update_device_console(
    target_device_id: str, console_id: str, req: ConsoleFoldersRequest,
    device_id: str = Depends(_auth),
) -> dict:
    """Edit one of the caller's own console rows (#539, #642).

    Cross-device validation: when ``import_remote_path`` is set, all other
    devices must agree on the same remote path for the same console name.
    """
    if target_device_id != device_id:
        raise HTTPException(status_code=403, detail="Can only edit this device's consoles")
    store = _get_store()
    console = next((c for c in store.list_consoles(device_id) if c.id == console_id), None)
    if not console:
        raise HTTPException(status_code=404, detail="Console not found")

    # Cross-device validation for import_remote_path (#642).
    if req.import_remote_path:
        for other_device in store.list_devices():
            if other_device.id == device_id:
                continue
            for other_console in store.list_consoles(other_device.id):
                if (other_console.console_name == console.console_name
                        and other_console.import_remote_path
                        and other_console.import_remote_path != req.import_remote_path):
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Remote path mismatch for {console.console_name}: "
                            f"another device uses '{other_console.import_remote_path}'"
                        ),
                    )

    for field, value in req.model_dump(exclude_none=True).items():
        setattr(console, field, value)
    if req.device_extra_folders is not None:
        seen = {console.device_game_folder}
        console.device_extra_folders = [
            f for f in (x.strip() for x in req.device_extra_folders)
            if f and not (f in seen or seen.add(f))
        ]
    store.set_console(console)
    return {"ok": True}


# ── device game-devices (any device) ─────────────────────────────────────────

@router.get("/devices/{target_device_id}/game-devices")
def get_device_game_devices(target_device_id: str, device_id: str = Depends(_auth)) -> list[dict]:
    """Return all games configured for a specific device."""
    return _get_store().list_game_devices_for_device(target_device_id)
