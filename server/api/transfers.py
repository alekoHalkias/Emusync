"""ROM transfers, ROM pull requests, and the SSE event stream that notifies
devices about both."""
from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

import asyncio

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from ._core import (
    _auth,
    _get_store,
    _print_activity,
    _device_label,
    _game_label,
    get_data_dir,
    _remove_staging_dir,
    _online_devices,
    _presence_lock,
    _device_event_queues,
)

router = APIRouter()


# ── rom transfers ─────────────────────────────────────────────────────────────

@router.post("/games/{slug}/rom-transfer")
async def create_rom_transfer(
    slug: str,
    request: Request,
    x_to_device_id: str = Header(None),
    x_destination_path: str = Header(None),
    x_filename: str = Header("rom"),
    device_id: str = Depends(_auth),
) -> dict:
    store = _get_store()
    game = store.get_game(slug)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if not x_to_device_id:
        raise HTTPException(status_code=400, detail="Missing X-To-Device-ID header")
    data_dir = get_data_dir()
    if not data_dir:
        raise HTTPException(status_code=500, detail="Server data directory not configured")

    devices = store.list_devices()
    if not any(d.id == x_to_device_id for d in devices):
        raise HTTPException(status_code=404, detail="Target device not found")

    transfer_id = str(uuid.uuid4())
    filename = x_filename or "rom"
    transfer_subdir = Path(data_dir) / "rom_staging" / transfer_id
    transfer_subdir.mkdir(parents=True, exist_ok=True)
    staged_path = transfer_subdir / filename

    loop = asyncio.get_running_loop()
    hasher = hashlib.sha256()
    with open(staged_path, "wb") as f:
        async for chunk in request.stream():
            hasher.update(chunk)
            await loop.run_in_executor(None, f.write, chunk)
    sha256 = hasher.hexdigest()

    store.create_rom_transfer(
        id=transfer_id,
        slug=slug,
        from_device_id=device_id,
        to_device_id=x_to_device_id,
        destination_path=x_destination_path or "",
        staged_file=str(staged_path),
        sha256=sha256,
    )

    target_name = next((d.name for d in devices if d.id == x_to_device_id), x_to_device_id)
    with _presence_lock:
        is_online = x_to_device_id in _online_devices

    # Notify target device via SSE if it has a stream open
    if x_to_device_id in _device_event_queues:
        await _device_event_queues[x_to_device_id].put({
            "type": "rom_transfer_queued",
            "transfer_id": transfer_id,
            "slug": slug,
            "game_name": game.name,
            "console": game.console,
            "destination_path": x_destination_path or "",
            "sha256": sha256,
        })

    store.log_event("rom_transfer_queued", slug, device_id)
    _print_activity(
        f"ROM pushed: {game.name} from {_device_label(device_id)} → {target_name} (queued)"
    )

    return {"transfer_id": transfer_id, "status": "pending", "target_online": is_online}


# ── rom transfer delivery ─────────────────────────────────────────────────────

@router.get("/rom-transfers/pending")
def list_pending_transfers(device_id: str = Depends(_auth)) -> list[dict]:
    """Return all pending ROM transfers queued for the calling device."""
    store = _get_store()
    transfers = store.list_pending_transfers_for_device(device_id)
    result = []
    for t in transfers:
        game = store.get_game(t.slug)
        result.append({
            "id": t.id,
            "slug": t.slug,
            "destination_path": t.destination_path,
            "queued_at": t.queued_at,
            "console": game.console if game else "",
            "game_name": game.name if game else t.slug,
            "sha256": t.sha256,
        })
    return result


@router.get("/rom-transfers/{transfer_id}/file")
def download_transfer_file(transfer_id: str, device_id: str = Depends(_auth)) -> FileResponse:
    """Stream the staged ROM file for a pending transfer."""
    transfer = _get_store().get_rom_transfer(transfer_id)
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfer not found")
    if transfer.to_device_id != device_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    staged = Path(transfer.staged_file)
    if not staged.exists():
        raise HTTPException(status_code=410, detail="Staged file no longer exists")
    _print_activity(f"ROM pulled: {_game_label(transfer.slug)} by {_device_label(device_id)}")
    headers = {"X-Rom-Hash": transfer.sha256} if transfer.sha256 else None
    return FileResponse(str(staged), filename=staged.name, media_type="application/octet-stream", headers=headers)


@router.put("/rom-transfers/{transfer_id}")
def update_transfer(transfer_id: str, request_body: dict, device_id: str = Depends(_auth)) -> dict:
    """Mark a transfer as completed or failed."""
    transfer = _get_store().get_rom_transfer(transfer_id)
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfer not found")
    if transfer.to_device_id != device_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    status = request_body.get("status", "completed")
    if status not in ("completed", "failed"):
        raise HTTPException(status_code=400, detail="status must be 'completed' or 'failed'")
    _get_store().update_transfer_status(transfer_id, status)
    # Transfer is delivered (or dead) — reclaim its staged file.
    _remove_staging_dir(transfer.staged_file)
    return {"ok": True}


# ── rom pull requests ─────────────────────────────────────────────────────────

@router.post("/games/{slug}/rom-pull-request")
async def create_pull_request(
    slug: str,
    request_body: dict,
    device_id: str = Depends(_auth),
) -> dict:
    """Request a ROM from another device. The source device uploads it when online."""
    store = _get_store()
    game = store.get_game(slug)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    from_device_id = request_body.get("from_device_id")
    destination_path = request_body.get("destination_path", "")
    if not from_device_id:
        raise HTTPException(status_code=400, detail="Missing from_device_id")

    devices = store.list_devices()
    if not any(d.id == from_device_id for d in devices):
        raise HTTPException(status_code=404, detail="Source device not found")

    pull_request_id = str(uuid.uuid4())
    store.create_pull_request(
        id=pull_request_id,
        slug=slug,
        from_device_id=from_device_id,
        to_device_id=device_id,
        destination_path=destination_path,
    )

    with _presence_lock:
        source_online = from_device_id in _online_devices

    # Notify source device via SSE if it has a stream open
    if from_device_id in _device_event_queues:
        await _device_event_queues[from_device_id].put({
            "type": "rom_pull_requested",
            "pull_request_id": pull_request_id,
            "slug": slug,
            "game_name": game.name,
            "console": game.console,
            "to_device_id": device_id,
            "destination_path": destination_path,
        })

    source_name = next((d.name for d in devices if d.id == from_device_id), from_device_id)
    _print_activity(f"ROM pull requested: {game.name} ← {source_name}")

    return {"pull_request_id": pull_request_id, "status": "pending", "source_online": source_online}


@router.get("/rom-pull-requests/pending")
def list_pending_pull_requests(device_id: str = Depends(_auth)) -> list[dict]:
    """Return pending pull requests where the calling device is the source."""
    store = _get_store()
    requests = store.list_pending_pull_requests_for_device(device_id)
    result = []
    for pr in requests:
        game = store.get_game(pr.slug)
        result.append({
            "id": pr.id,
            "slug": pr.slug,
            "to_device_id": pr.to_device_id,
            "destination_path": pr.destination_path,
            "requested_at": pr.requested_at,
            "console": game.console if game else "",
            "game_name": game.name if game else pr.slug,
        })
    return result


@router.put("/rom-pull-requests/{pull_request_id}")
def update_pull_request(pull_request_id: str, request_body: dict, device_id: str = Depends(_auth)) -> dict:
    """Mark a pull request as fulfilled or failed. Only the source device can update it."""
    pr = _get_store().get_pull_request(pull_request_id)
    if not pr:
        raise HTTPException(status_code=404, detail="Pull request not found")
    if pr.from_device_id != device_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    status = request_body.get("status", "fulfilled")
    if status not in ("fulfilled", "failed"):
        raise HTTPException(status_code=400, detail="status must be 'fulfilled' or 'failed'")
    _get_store().update_pull_request_status(pull_request_id, status)
    return {"ok": True}


# ── SSE event stream ──────────────────────────────────────────────────────────

@router.get("/events/stream")
async def stream_events_sse(device_id: str = Depends(_auth)) -> StreamingResponse:
    """Server-Sent Events stream — delivers real-time notifications to a device."""
    queue: asyncio.Queue = asyncio.Queue()
    _device_event_queues[device_id] = queue

    async def generator():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                except asyncio.CancelledError:
                    return  # server shutting down — close the stream cleanly
        except GeneratorExit:
            pass
        finally:
            _device_event_queues.pop(device_id, None)

    return StreamingResponse(generator(), media_type="text/event-stream")
