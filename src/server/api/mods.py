"""Communal Switch mod pool sync (issue #444).

Keyed by title ID (not game slug or device) since a mod folder under Eden's
``load/<title-id>/`` is shared across every device that has the game, the same
way `switch_title_id` itself is shared on the `games` row (#443).
"""
from __future__ import annotations

import asyncio
import hashlib

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import FileResponse

from ._core import _auth, _get_store, _print_activity, _device_label

router = APIRouter()


@router.get("/switch/{title_id}/mods")
def list_switch_mods(title_id: str, device_id: str = Depends(_auth)) -> list[dict]:
    return _get_store().list_switch_mods(title_id)


@router.get("/switch/{title_id}/mods/{mod_name}")
def pull_switch_mod(title_id: str, mod_name: str, device_id: str = Depends(_auth)) -> Response:
    path = _get_store().get_switch_mod_path(title_id, mod_name)
    if path is None:
        return Response(status_code=204)
    _print_activity(f"mod pulled: {mod_name} ({title_id}) by {_device_label(device_id)}")
    return FileResponse(path, media_type="application/octet-stream")


@router.post("/switch/{title_id}/mods/{mod_name}")
async def push_switch_mod(title_id: str, mod_name: str, request: Request, device_id: str = Depends(_auth)) -> dict:
    store = _get_store()
    tmp = store.new_upload_path()
    hasher = hashlib.sha256()
    size = 0
    try:
        with open(tmp, "wb") as f:
            async for chunk in request.stream():
                f.write(chunk)
                hasher.update(chunk)
                size += len(chunk)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise

    def _store_it() -> bool:
        return store.add_switch_mod(title_id, mod_name, device_id, tmp, size)

    added = await asyncio.to_thread(_store_it)
    if added:
        _print_activity(f"mod pushed: {mod_name} ({title_id}) from {_device_label(device_id)}")
    return {"added": added}
