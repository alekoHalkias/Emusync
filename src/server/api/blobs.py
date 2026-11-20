"""Save and state blob sync: pull/push, metadata, history, and rollback (#7).

States mirror saves at every endpoint, so both sets of routes are thin wrappers
over the shared `_BlobKind`-parametrised handlers below (issue #240). The store
exposes a uniform method set per kind (`pull_<noun>_path`, `push_<noun>_file`,
`get_<noun>_meta`, `list_<noun>_history`, `restore_<noun>`), so a handler only
needs the noun to dispatch."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel

from ..store import SaveMeta
from ..blob_tree import manifest_size, verify_blob
from ._core import (
    _auth, _get_store, _print_activity, _device_label, _game_label,
    _run_integrity_sweep, get_integrity_status,
)

router = APIRouter()

# ponytail: fixed ceiling for save/state/memcard pushes, make it a Config field if users hit it (#704)
_MAX_UPLOAD_BYTES = 4 * 1024**3


class RestoreRequest(BaseModel):
    version_id: str


@dataclass(frozen=True)
class _BlobKind:
    """What differs between the save, state and console-memcard route families."""
    noun: str          # "save" / "state" / "console_save" — drives the store method names
    hash_header: str   # response header carrying the content hash on pull
    synced_event: Optional[str] = None  # event-log type recorded on push (None: no event)
    console: bool = False  # owner is a console_key, not a game slug; also carries X-Card-Format (#737)
    label: str = ""    # word used in activity logs / default 404 text; defaults to noun
    baseline: str = ""  # store method suffix for this kind's sync baseline, "" = none (states)
    not_found: str = ""  # restore 404 text; defaults to "<Noun> version not found"


_SAVE = _BlobKind(noun="save", hash_header="X-Save-Hash", synced_event="save_synced", baseline="save_sync_baseline")
_STATE = _BlobKind(noun="state", hash_header="X-State-Hash", synced_event="state_synced")
# Shared console memory card (#295): same handlers, keyed by console_key. Hash header stays
# X-Save-Hash and the 404 text stays "Memory card version not found" (wire compatibility).
_CARD = _BlobKind(noun="console_save", hash_header="X-Save-Hash", console=True, label="memcard",
                  baseline="console_save_sync_baseline", not_found="Memory card version not found")


# ── shared handlers (parametrised by kind) ─────────────────────────────────────

def _f(meta, key: str):
    """Field of a store meta: SaveMeta (games) or dict (console cards)."""
    return meta[key] if isinstance(meta, dict) else getattr(meta, key)


def _owner_label(kind: _BlobKind, key: str) -> str:
    return key if kind.console else _game_label(key)


def _pull(kind: _BlobKind, slug: str, device_id: str) -> Response:
    store = _get_store()
    path, meta = getattr(store, f"pull_{kind.noun}_path")(slug)
    if path is None:
        return Response(status_code=204)
    _print_activity(f"{kind.label or kind.noun} pulled: {_owner_label(kind, slug)} by {_device_label(device_id)}")
    background = None
    if kind.baseline:
        # This device's copy agrees with the server as of this hash once the body
        # is delivered — record it then (not before), so an aborted download can't
        # hide a real conflict (#460, #481, #715).
        background = BackgroundTask(
            getattr(store, f"set_{kind.baseline}"), slug, device_id, _f(meta, "hash"), _f(meta, "pushed_at")
        )
    headers = {
        kind.hash_header: _f(meta, "hash"),
        "X-Pushed-At": _f(meta, "pushed_at"),
        "X-Device-Id": _f(meta, "device_id"),
    }
    if kind.console:
        headers["X-Card-Format"] = meta.get("card_format", "")
    # FileResponse streams from disk instead of loading the blob into memory.
    return FileResponse(path, media_type="application/octet-stream", headers=headers, background=background)


async def _push(kind: _BlobKind, slug: str, request: Request, device_id: str) -> dict:
    if not kind.console and not _get_store().get_game(slug):
        raise HTTPException(status_code=404, detail="Game not found")  # before staging (#701)
    tmp = await _stage_upload(request)
    extra = (request.headers.get("X-Card-Format", ""),) if kind.console else ()

    def _store_it():
        store = _get_store()
        h, size = _verify_upload(tmp)
        m = getattr(store, f"push_{kind.noun}_file")(slug, device_id, tmp, h, size, *extra)
        if kind.synced_event:
            store.log_event(kind.synced_event, slug, device_id)
        if kind.baseline:
            # The pushing device trivially agrees with the server on its own
            # push — record it as this device's baseline too (#460, #481).
            getattr(store, f"set_{kind.baseline}")(slug, device_id, _f(m, "hash"), _f(m, "pushed_at"))
        return m

    # Offload the synchronous move + DB write so it doesn't block the event loop.
    try:
        meta = await asyncio.to_thread(_store_it)
    except BaseException:
        tmp.unlink(missing_ok=True)  # failed push must not leak the staged upload (#701, #704)
        raise
    _print_activity(f"{kind.label or kind.noun} pushed: {_owner_label(kind, slug)} from {_device_label(device_id)}")
    return {"hash": _f(meta, "hash"), "pushed_at": _f(meta, "pushed_at")}


def _meta(kind: _BlobKind, slug: str) -> Response:
    meta = getattr(_get_store(), f"get_{kind.noun}_meta")(slug)
    if not meta:
        return Response(status_code=204)
    body = {"hash": _f(meta, "hash"), "pushed_at": _f(meta, "pushed_at"),
            "device_id": _f(meta, "device_id"), "size": _f(meta, "size")}
    if kind.console:
        body["card_format"] = meta.get("card_format", "")
    return Response(content=json.dumps(body), media_type="application/json")


def _sync_baseline(kind: _BlobKind, slug: str, device_id: str) -> Response:
    """The hash *this* device last successfully pushed or pulled for this game /
    console — lets it tell a real conflict from a routine catch-up pull (#460, #481)."""
    baseline = getattr(_get_store(), f"get_{kind.baseline}")(slug, device_id)
    if not baseline:
        return Response(status_code=204)
    return Response(content=json.dumps(baseline), media_type="application/json")


def _history(kind: _BlobKind, slug: str) -> list[dict]:
    store = _get_store()
    if not kind.console and not store.get_game(slug):
        raise HTTPException(status_code=404, detail="Game not found")
    return getattr(store, f"list_{kind.noun}_history")(slug)


def _restore(kind: _BlobKind, slug: str, version_id: str, device_id: str) -> dict:
    try:
        meta = getattr(_get_store(), f"restore_{kind.noun}")(slug, version_id)
    except ValueError:  # a generation the v38 conversion could not convert (#739)
        raise HTTPException(status_code=409, detail="That version is unreadable and cannot be restored")
    if not meta:
        raise HTTPException(status_code=404, detail=kind.not_found or f"{kind.noun.capitalize()} version not found")
    _print_activity(f"{kind.label or kind.noun} restored: {_owner_label(kind, slug)} by {_device_label(device_id)}")
    return {"hash": _f(meta, "hash"), "pushed_at": _f(meta, "pushed_at")}


async def _stage_upload(request: Request):
    """Stream the request body to a temp file under the blob root and return its
    path, so a multi-MB save/state is never held whole in memory (issue #239). The
    store moves the file into place on a same-filesystem rename; on a dedupe hit
    it's discarded. Hash and size come from the blob's manifest (_verify_upload)."""
    store = _get_store()
    loop = asyncio.get_running_loop()
    tmp = store.new_upload_path()
    size = 0
    try:
        with open(tmp, "wb") as f:
            async for chunk in request.stream():
                size += len(chunk)
                if size > _MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Upload too large")
                await loop.run_in_executor(None, f.write, chunk)  # keep disk I/O off the event loop (#715)
        if size == 0:
            raise HTTPException(status_code=400, detail="Empty upload")  # never store an empty generation (#715)
    except BaseException:
        tmp.unlink(missing_ok=True)  # don't leave a half-written .part behind
        raise
    return tmp


def _verify_upload(path) -> tuple[str, int]:
    """(content hash, content size) of a staged upload. Anything but a valid
    format-3 blob is a 400: old clients must update after the server (#739)."""
    try:
        m, h = verify_blob(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unsupported or corrupt save data ({exc}); update the EmuSync client")
    return h, manifest_size(m)


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


@router.get("/games/{slug}/save/sync-baseline")
def get_save_sync_baseline(slug: str, device_id: str = Depends(_auth)) -> Response:
    """The save hash *this* device (from its auth header) last successfully
    pushed or pulled for this game — lets it tell a real conflict apart from a
    routine catch-up pull (issue #460)."""
    return _sync_baseline(_SAVE, slug, device_id)


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


# ── console-scoped shared save (memory card, issue #295) ─────────────────────────
# One memory card per console (PS2), shared across every game on that console.
# Same handlers as the per-game save routes (kind _CARD), keyed by console_key (#737).

@router.get("/consoles/{console_key}/memcard")
def pull_console_memcard(console_key: str, device_id: str = Depends(_auth)) -> Response:
    return _pull(_CARD, console_key, device_id)


@router.post("/consoles/{console_key}/memcard")
async def push_console_memcard(console_key: str, request: Request, device_id: str = Depends(_auth)) -> dict:
    return await _push(_CARD, console_key, request, device_id)


@router.get("/consoles/{console_key}/memcard/meta")
def get_console_memcard_meta(console_key: str, device_id: str = Depends(_auth)) -> Response:
    return _meta(_CARD, console_key)


@router.get("/consoles/{console_key}/memcard/sync-baseline")
def get_console_memcard_sync_baseline(console_key: str, device_id: str = Depends(_auth)) -> Response:
    """The shared-card hash *this* device last successfully pushed or pulled
    for CONSOLE_KEY, the same as /games/{slug}/save/sync-baseline (#460/#481)."""
    return _sync_baseline(_CARD, console_key, device_id)


@router.get("/consoles/{console_key}/memcard/history")
def list_console_memcard_history(console_key: str, device_id: str = Depends(_auth)) -> list[dict]:
    """Every retained generation of a console's shared card, newest first (#480)."""
    return _history(_CARD, console_key)


@router.post("/consoles/{console_key}/memcard/restore")
def restore_console_memcard(console_key: str, req: RestoreRequest, device_id: str = Depends(_auth)) -> dict:
    """Make a past generation of a console's shared card current (#480)."""
    return _restore(_CARD, console_key, req.version_id, device_id)

