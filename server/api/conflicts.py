"""Save-conflict records for the GUI Conflicts panel (issue #243).

`emusync run` reports an auto-resolved divergence here; the renderer lists open
conflicts and dismisses them once handled. Recovery itself reuses the existing
save history/restore routes — these endpoints only track that a conflict happened.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
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


@router.post("/consoles/{console_key}/conflicts")
def report_console_conflict(console_key: str, req: ConflictReport, device_id: str = Depends(_auth)) -> dict:
    """Console-key equivalent of report_conflict for a shared-memcard console's
    card (#482) — no game row to check, console_key is just a string."""
    rec = _get_store().add_console_conflict(
        console_key, req.winner_device_id, req.loser_device_id, req.winner_hash, req.loser_hash,
    )
    _print_activity(f"save conflict on {console_key} memory card resolved (reported by {_device_label(device_id)})")
    return {"id": rec["id"], "resolved_at": rec["resolved_at"]}


@router.get("/conflicts")
def list_conflicts(device_id: str = Depends(_auth)) -> list[dict]:
    """All open (un-dismissed) conflicts across games AND shared-memcard
    consoles, newest first (#482)."""
    return _get_store().list_open_conflicts()


@router.post("/conflicts/{conflict_id}/dismiss")
def dismiss_conflict(conflict_id: str, device_id: str = Depends(_auth)) -> dict:
    if not _get_store().dismiss_conflict(conflict_id):
        raise HTTPException(status_code=404, detail="Conflict not found or already dismissed")
    return {"ok": True}


@router.get("/games/{slug}/conflicts/check")
def check_save_conflict(
    slug: str,
    local_hash: str = Query(),
    device_id: str = Depends(_auth),
) -> dict:
    """Check whether the local save hash diverges from the server (issue #579).

    Returns divergence info the GUI uses for a side-by-side conflict modal.
    A true divergence = BOTH sides moved past the sync baseline and have
    different hashes (same logic as ``cli/run_reconcile.py``).
    """
    store = _get_store()
    if not store.get_game(slug):
        raise HTTPException(status_code=404, detail="Game not found")
    server_meta = store.get_save_meta(slug)
    baseline = store.get_save_sync_baseline(slug, device_id)

    baseline_hash = baseline.get("hash") if baseline else None
    server_hash = server_meta.hash if server_meta else None

    # True divergence: both sides moved past baseline and differ.
    local_changed = local_hash != baseline_hash
    server_changed = server_hash is not None and server_hash != baseline_hash
    diverged = local_changed and server_changed and local_hash != server_hash

    if diverged:
        return {
            "diverged": True,
            "local_hash": local_hash,
            "server_hash": server_hash,
            "server_pushed_at": server_meta.pushed_at if server_meta else None,
            "baseline_hash": baseline_hash,
            "baseline_synced_at": baseline.get("synced_at") if baseline else None,
        }
    return {"diverged": False}


@router.get("/games/{slug}/state/conflicts/check")
def check_state_conflict(
    slug: str,
    local_hash: str = Query(),
    device_id: str = Depends(_auth),
) -> dict:
    """Check whether the local state hash diverges from the server (issue #579).

    Same logic as ``check_save_conflict`` but for state blobs.
    States don't have a per-device baseline table, so divergence is
    detected by hash mismatch only.
    """
    store = _get_store()
    if not store.get_game(slug):
        raise HTTPException(status_code=404, detail="Game not found")
    server_meta = store.get_state_meta(slug)
    server_hash = server_meta.hash if server_meta else None
    diverged = local_hash != server_hash

    if diverged and server_meta:
        return {
            "diverged": True,
            "local_hash": local_hash,
            "server_hash": server_hash,
            "server_pushed_at": server_meta.pushed_at,
            "baseline_hash": None,
            "baseline_synced_at": None,
        }
    return {"diverged": False}
