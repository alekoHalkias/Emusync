"""Communal Switch mod pool sync (issue #444).

Keyed by title ID (not game slug or device) since a mod folder under Eden's
``load/<title-id>/`` is shared across every device that has the game, the same
way `switch_title_id` itself is shared on the `games` row (#443).
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import FileResponse

from .blobs import _verify_upload
from ._core import _auth, _get_store, _print_activity, _device_label, _safe_segment

router = APIRouter()


@router.get("/switch/{title_id}/mods")
def list_switch_mods(title_id: str, device_id: str = Depends(_auth)) -> list[dict]:
    _safe_segment(title_id, "title_id")
    return _get_store().list_switch_mods(title_id)


@router.get("/switch/{title_id}/mods/{mod_name}")
def pull_switch_mod(title_id: str, mod_name: str, device_id: str = Depends(_auth)) -> Response:
    _safe_segment(title_id, "title_id")
    _safe_segment(mod_name, "mod_name")
    path = _get_store().get_switch_mod_path(title_id, mod_name)
    if path is None:
        return Response(status_code=204)
    _print_activity(f"mod pulled: {mod_name} ({title_id}) by {_device_label(device_id)}")
    return FileResponse(path, media_type="application/octet-stream")


@router.post("/switch/{title_id}/mods/{mod_name}")
async def push_switch_mod(title_id: str, mod_name: str, request: Request, device_id: str = Depends(_auth)) -> dict:
    _safe_segment(title_id, "title_id")
    _safe_segment(mod_name, "mod_name")
    store = _get_store()
    tmp = store.new_upload_path()
    try:
        with open(tmp, "wb") as f:
            async for chunk in request.stream():
                f.write(chunk)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise

    def _store_it() -> bool:
        _, content_size = _verify_upload(tmp)  # 400 unless a valid format-3 blob (#739)
        return store.add_switch_mod(title_id, mod_name, device_id, tmp, content_size)

    try:
        added = await asyncio.to_thread(_store_it)
    finally:
        tmp.unlink(missing_ok=True)  # moved into place on success; never leak a staged upload (#704)
    if added:
        _print_activity(f"mod pushed: {mod_name} ({title_id}) from {_device_label(device_id)}")
    return {"added": added}
