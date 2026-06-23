"""Save-conflict records for the GUI Conflicts panel (issue #243).

`emusync run` reports an auto-resolved divergence here; the renderer lists open
conflicts and dismisses them once handled. Recovery itself reuses the existing
save history/restore routes — these endpoints only track that a conflict happened.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ._core import _auth, _get_store, _print_activity, _device_label, _game_label

router = APIRouter()


class ConflictReport(BaseModel):
    winner_device_id: str = ""
    loser_device_id: str = ""
    winner_hash: str = ""
    loser_hash: str = ""


@router.post("/games/{slug}/conflicts")
def report_conflict(slug: str, req: ConflictReport, device_id: str = Depends(_auth)) -> dict:
    store = _get_store()
    if not store.get_game(slug):
        raise HTTPException(status_code=404, detail="Game not found")
    rec = store.add_conflict(
        slug, req.winner_device_id, req.loser_device_id, req.winner_hash, req.loser_hash,
    )
    _print_activity(f"save conflict on {_game_label(slug)} resolved (reported by {_device_label(device_id)})")
    return {"id": rec["id"], "resolved_at": rec["resolved_at"]}


@router.get("/conflicts")
def list_conflicts(device_id: str = Depends(_auth)) -> list[dict]:
    """All open (un-dismissed) conflicts across games, newest first."""
    return _get_store().list_open_conflicts()


@router.post("/conflicts/{conflict_id}/dismiss")
def dismiss_conflict(conflict_id: str, device_id: str = Depends(_auth)) -> dict:
    if not _get_store().dismiss_conflict(conflict_id):
        raise HTTPException(status_code=404, detail="Conflict not found or already dismissed")
    return {"ok": True}
