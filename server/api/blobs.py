"""Save and state blob sync: pull/push, metadata, history, and rollback (#7).

States mirror saves at every endpoint."""
from __future__ import annotations

import hashlib
import json

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..store import SaveMeta
from ._core import _auth, _get_store, _print_activity, _device_label, _game_label

router = APIRouter()


class RestoreRequest(BaseModel):
    version_id: str


async def _stage_upload(request: Request):
    """Stream the request body to a temp file under the blob root, hashing as we go.

    Returns (path, sha256_hex, size) so a multi-MB save/state is never held whole in
    memory (issue #239). The store moves the file into place on a same-filesystem
    rename; on a dedupe hit it's discarded.
    """
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
        tmp.unlink(missing_ok=True)  # don't leave a half-written .part behind
        raise
    return tmp, hasher.hexdigest(), size


# ── saves ─────────────────────────────────────────────────────────────────────

@router.get("/games/{slug}/save")
def pull_save(slug: str, device_id: str = Depends(_auth)) -> Response:
    path, meta = _get_store().pull_save_path(slug)
    if path is None:
        return Response(status_code=204)
    _print_activity(f"save pulled: {_game_label(slug)} by {_device_label(device_id)}")
    # FileResponse streams from disk instead of loading the blob into memory.
    return FileResponse(
        path,
        media_type="application/octet-stream",
        headers={
            "X-Save-Hash": meta.hash,
            "X-Pushed-At": meta.pushed_at,
            "X-Device-Id": meta.device_id,
        },
    )


@router.post("/games/{slug}/save")
async def push_save(slug: str, request: Request, device_id: str = Depends(_auth)) -> dict:
    tmp, h, size = await _stage_upload(request)

    def _store_save() -> SaveMeta:
        store = _get_store()
        m = store.push_save_file(slug, device_id, tmp, h, size)
        store.log_event("save_synced", slug, device_id)
        return m

    # Offload the synchronous move + DB write so it doesn't block the event loop.
    meta = await asyncio.to_thread(_store_save)
    _print_activity(f"save pushed: {_game_label(slug)} from {_device_label(device_id)}")
    return {"hash": meta.hash, "pushed_at": meta.pushed_at}


@router.get("/games/{slug}/save/meta")
def get_save_meta(slug: str, device_id: str = Depends(_auth)) -> Response:
    meta = _get_store().get_save_meta(slug)
    if not meta:
        return Response(status_code=204)
    return Response(
        content=json.dumps({"hash": meta.hash, "pushed_at": meta.pushed_at, "device_id": meta.device_id, "size": meta.size}),
        media_type="application/json",
    )


@router.get("/games/{slug}/save/history")
def list_save_history(slug: str, device_id: str = Depends(_auth)) -> list[dict]:
    """Every retained save generation for a game, newest first (issue #7)."""
    if not _get_store().get_game(slug):
        raise HTTPException(status_code=404, detail="Game not found")
    return _get_store().list_save_history(slug)


@router.post("/games/{slug}/save/restore")
def restore_save(slug: str, req: RestoreRequest, device_id: str = Depends(_auth)) -> dict:
    """Make a past save generation current (it becomes the next thing pulled)."""
    meta = _get_store().restore_save(slug, req.version_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Save version not found")
    _print_activity(f"save restored: {_game_label(slug)} by {_device_label(device_id)}")
    return {"hash": meta.hash, "pushed_at": meta.pushed_at}


# ── states ────────────────────────────────────────────────────────────────────

@router.get("/games/{slug}/state")
def pull_state(slug: str, device_id: str = Depends(_auth)) -> Response:
    path, meta = _get_store().pull_state_path(slug)
    if path is None:
        return Response(status_code=204)
    _print_activity(f"state pulled: {_game_label(slug)} by {_device_label(device_id)}")
    return FileResponse(
        path,
        media_type="application/octet-stream",
        headers={
            "X-State-Hash": meta.hash,
            "X-Pushed-At": meta.pushed_at,
            "X-Device-Id": meta.device_id,
        },
    )


@router.post("/games/{slug}/state")
async def push_state(slug: str, request: Request, device_id: str = Depends(_auth)) -> dict:
    tmp, h, size = await _stage_upload(request)

    def _store_state() -> SaveMeta:
        store = _get_store()
        m = store.push_state_file(slug, device_id, tmp, h, size)
        store.log_event("state_synced", slug, device_id)
        return m

    # Offload the synchronous move + DB write so it doesn't block the event loop.
    meta = await asyncio.to_thread(_store_state)
    _print_activity(f"state pushed: {_game_label(slug)} from {_device_label(device_id)}")
    return {"hash": meta.hash, "pushed_at": meta.pushed_at}


@router.get("/games/{slug}/state/meta")
def get_state_meta(slug: str, device_id: str = Depends(_auth)) -> Response:
    meta = _get_store().get_state_meta(slug)
    if not meta:
        return Response(status_code=204)
    return Response(
        content=json.dumps({"hash": meta.hash, "pushed_at": meta.pushed_at, "device_id": meta.device_id, "size": meta.size}),
        media_type="application/json",
    )


@router.get("/games/{slug}/state/history")
def list_state_history(slug: str, device_id: str = Depends(_auth)) -> list[dict]:
    """Every retained state generation for a game, newest first (issue #7)."""
    if not _get_store().get_game(slug):
        raise HTTPException(status_code=404, detail="Game not found")
    return _get_store().list_state_history(slug)


@router.post("/games/{slug}/state/restore")
def restore_state(slug: str, req: RestoreRequest, device_id: str = Depends(_auth)) -> dict:
    """Make a past state generation current (it becomes the next thing pulled)."""
    meta = _get_store().restore_state(slug, req.version_id)
    if not meta:
        raise HTTPException(status_code=404, detail="State version not found")
    _print_activity(f"state restored: {_game_label(slug)} by {_device_label(device_id)}")
    return {"hash": meta.hash, "pushed_at": meta.pushed_at}
