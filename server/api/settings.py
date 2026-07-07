"""Server-wide settings (issue #322) — currently just the shared SteamGridDB
API key. Entered once on the server device (see gui's Setup.tsx onboarding
step and ServerStatusButton's settings panel) and fetched by every device's
Electron process, since SteamGridDB has no OAuth/programmatic flow for a
per-user key.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ._core import _auth, _get_store

router = APIRouter()

_STEAMGRIDDB_KEY = "steamgriddb_api_key"


class SteamGridDbKey(BaseModel):
    api_key: str = ""


@router.get("/settings/steamgriddb-key")
def get_steamgriddb_key(device_id: str = Depends(_auth)) -> dict:
    return {"api_key": _get_store().get_setting(_STEAMGRIDDB_KEY)}


@router.put("/settings/steamgriddb-key")
def set_steamgriddb_key(req: SteamGridDbKey, device_id: str = Depends(_auth)) -> dict:
    _get_store().set_setting(_STEAMGRIDDB_KEY, req.api_key)
    return {"ok": True}
