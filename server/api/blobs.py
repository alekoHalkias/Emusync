"""Save and state blob sync: pull/push, metadata, history, and rollback (#7).

States mirror saves at every endpoint, so both sets of routes are thin wrappers
over the shared `_BlobKind`-parametrised handlers below (issue #240). The store
exposes a uniform method set per kind (`pull_<noun>_path`, `push_<noun>_file`,
`get_<noun>_meta`, `list_<noun>_history`, `restore_<noun>`), so a handler only
needs the noun to dispatch."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..store import SaveMeta
from ._core import (
    _auth, _get_store, _print_activity, _device_label, _game_label,
    _run_integrity_sweep, get_integrity_status,
)

router = APIRouter()


class RestoreRequest(BaseModel):
    version_id: str


@dataclass(frozen=True)
class _BlobKind:
    """What differs between the save and state route families."""
    noun: str          # "save" / "state" — also drives the store method names
    hash_header: str   # response header carrying the content hash on pull
    synced_event: str  # event-log type recorded on push


_SAVE = _BlobKind(noun="save", hash_header="X-Save-Hash", synced_event="save_synced")
_STATE = _BlobKind(noun="state", hash_header="X-State-Hash", synced_event="state_synced")


# ── shared handlers (parametrised by kind) ─────────────────────────────────────

def _pull(kind: _BlobKind, slug: str, device_id: str) -> Response:
    path, meta = getattr(_get_store(), f"pull_{kind.noun}_path")(slug)
    if path is None:
        return Response(status_code=204)
    _print_activity(f"{kind.noun} pulled: {_game_label(slug)} by {_device_label(device_id)}")
    # FileResponse streams from disk instead of loading the blob into memory.
    return FileResponse(
        path,
        media_type="application/octet-stream",
        headers={
            kind.hash_header: meta.hash,
            "X-Pushed-At": meta.pushed_at,
            "X-Device-Id": meta.device_id,
        },
    )


async def _push(kind: _BlobKind, slug: str, request: Request, device_id: str) -> dict:
    tmp, h, size = await _stage_upload(request)

    def _store_it() -> SaveMeta:
        store = _get_store()
        m = getattr(store, f"push_{kind.noun}_file")(slug, device_id, tmp, h, size)
        store.log_event(kind.synced_event, slug, device_id)
        return m

    # Offload the synchronous move + DB write so it doesn't block the event loop.
    meta = await asyncio.to_thread(_store_it)
    _print_activity(f"{kind.noun} pushed: {_game_label(slug)} from {_device_label(device_id)}")
    return {"hash": meta.hash, "pushed_at": meta.pushed_at}


def _meta(kind: _BlobKind, slug: str) -> Response:
    meta = getattr(_get_store(), f"get_{kind.noun}_meta")(slug)
    if not meta:
        return Response(status_code=204)
    return Response(
        content=json.dumps({"hash": meta.hash, "pushed_at": meta.pushed_at, "device_id": meta.device_id, "size": meta.size}),
        media_type="application/json",
    )


def _history(kind: _BlobKind, slug: str) -> list[dict]:
    store = _get_store()
    if not store.get_game(slug):
        raise HTTPException(status_code=404, detail="Game not found")
    return getattr(store, f"list_{kind.noun}_history")(slug)


def _restore(kind: _BlobKind, slug: str, version_id: str, device_id: str) -> dict:
    meta = getattr(_get_store(), f"restore_{kind.noun}")(slug, version_id)
    if not meta:
        raise HTTPException(status_code=404, detail=f"{kind.noun.capitalize()} version not found")
    _print_activity(f"{kind.noun} restored: {_game_label(slug)} by {_device_label(device_id)}")
    return {"hash": meta.hash, "pushed_at": meta.pushed_at}


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
    return _pull(_SAVE, slug, device_id)


@router.post("/games/{slug}/save")
async def push_save(slug: str, request: Request, device_id: str = Depends(_auth)) -> dict:
    return await _push(_SAVE, slug, request, device_id)


@router.get("/games/{slug}/save/meta")
def get_save_meta(slug: str, device_id: str = Depends(_auth)) -> Response:
    return _meta(_SAVE, slug)


@router.get("/games/{slug}/save/history")
def list_save_history(slug: str, device_id: str = Depends(_auth)) -> list[dict]:
    """Every retained save generation for a game, newest first (issue #7)."""
    return _history(_SAVE, slug)


@router.post("/games/{slug}/save/restore")
def restore_save(slug: str, req: RestoreRequest, device_id: str = Depends(_auth)) -> dict:
    """Make a past save generation current (it becomes the next thing pulled)."""
    return _restore(_SAVE, slug, req.version_id, device_id)


# ── states ────────────────────────────────────────────────────────────────────

@router.get("/games/{slug}/state")
def pull_state(slug: str, device_id: str = Depends(_auth)) -> Response:
    return _pull(_STATE, slug, device_id)


@router.post("/games/{slug}/state")
async def push_state(slug: str, request: Request, device_id: str = Depends(_auth)) -> dict:
    return await _push(_STATE, slug, request, device_id)


@router.get("/games/{slug}/state/meta")
def get_state_meta(slug: str, device_id: str = Depends(_auth)) -> Response:
    return _meta(_STATE, slug)


@router.get("/games/{slug}/state/history")
def list_state_history(slug: str, device_id: str = Depends(_auth)) -> list[dict]:
    """Every retained state generation for a game, newest first (issue #7)."""
    return _history(_STATE, slug)


@router.post("/games/{slug}/state/restore")
def restore_state(slug: str, req: RestoreRequest, device_id: str = Depends(_auth)) -> dict:
    """Make a past state generation current (it becomes the next thing pulled)."""
    return _restore(_STATE, slug, req.version_id, device_id)


# ── integrity (issue #285) ──────────────────────────────────────────────────────

@router.get("/games/{slug}/integrity")
def get_game_integrity(slug: str, device_id: str = Depends(_auth)) -> dict:
    """Integrity verdicts for a game's current save + state blobs.

    Recomputed on demand (cheap) so the badge is correct immediately after a
    restore, without waiting for a full sweep. The literal `/integrity` tail
    keeps this clear of the `/games/overview` vs `/games/{slug}` collision.
    """
    store = _get_store()
    if not store.get_game(slug):
        raise HTTPException(status_code=404, detail="Game not found")
    return store.integrity_for_game(slug)


def _damaged_summary() -> list[dict]:
    out: list[dict] = []
    for slug, kinds in get_integrity_status().items():
        for kind, verdict in kinds.items():
            if verdict["status"] == "damaged":
                out.append({
                    "slug": slug,
                    "name": _game_label(slug),
                    "kind": kind,
                    "reasons": verdict["reasons"],
                    "last_good_version_id": verdict["last_good_version_id"],
                })
    return out


@router.get("/integrity")
def list_integrity(device_id: str = Depends(_auth)) -> dict:
    """Library-wide damaged-blob summary from the at-rest snapshot (no recompute)."""
    status = get_integrity_status()
    return {"scanned": len(status), "damaged": _damaged_summary()}


@router.post("/integrity/rescan")
def rescan_integrity(device_id: str = Depends(_auth)) -> dict:
    """Re-run the integrity sweep across all games and return the damaged ones."""
    _run_integrity_sweep()
    status = get_integrity_status()
    return {"scanned": len(status), "damaged": _damaged_summary()}
