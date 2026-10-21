"""Game metadata: cached Wikipedia fetch plus manual overrides (issue #578)."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException

from ..config import load
from ._core import _auth, _get_store

logger = logging.getLogger("emusync.api")
router = APIRouter()

WIKI_BASE = "https://en.wikipedia.org"  # module constant so tests can point it at a local stub
TTL = timedelta(days=30)
_HEADERS = {"User-Agent": "EmuSync/1.0 (LAN save sync; metadata fetch)"}
_EMPTY = {"synopsis": "", "release_date": "", "cover_url": "", "source": "", "fetched_at": ""}


def _get(client: httpx.Client, url: str, **params) -> dict | None:
    """GET JSON; one retry after 1s on 429/5xx. None on any failure."""
    for attempt in (0, 1):
        r = client.get(url, params=params)
        if r.status_code == 200:
            return r.json()
        if r.status_code not in (429, 500, 502, 503, 504) or attempt:
            return None
        time.sleep(1)
    return None


def fetch_wikipedia(name: str) -> dict | None:
    """Best-effort synopsis + cover for `name`. Never raises."""
    try:
        with httpx.Client(timeout=10, headers=_HEADERS) as c:
            found = _get(c, f"{WIKI_BASE}/w/rest.php/v1/search/title", q=f"{name} video game", limit=1)
            pages = (found or {}).get("pages") or []
            if not pages:
                return None
            s = _get(c, f"{WIKI_BASE}/api/rest_v1/page/summary/{quote(pages[0]['key'], safe='')}")
        if not s or not s.get("extract"):
            return None
        return {"synopsis": s["extract"], "cover_url": (s.get("thumbnail") or {}).get("source", "")}
    except Exception as e:  # network down, bad JSON, ...
        logger.debug("metadata fetch failed for %r: %s", name, e)
        return None


def _stale(row: dict) -> bool:
    return datetime.now(timezone.utc) - datetime.fromisoformat(row["fetched_at"]) > TTL


def _game_or_404(slug: str):
    game = _get_store().get_game(slug)
    if not game:
        raise HTTPException(status_code=404, detail=f"Game '{slug}' not found")
    return game


@router.get("/games/{slug}/metadata")
def get_metadata(slug: str, device_id: str = Depends(_auth)) -> dict:
    """Cached metadata; refetched when missing/stale (manual rows never are) and
    auto-fetch is enabled. Falls back to the stale row, then to empty fields."""
    game = _game_or_404(slug)
    store = _get_store()
    row = store.get_metadata(slug)
    if (row is None or (row["source"] != "manual" and _stale(row))) and load().auto_fetch_metadata:
        got = fetch_wikipedia(game.name)
        if got:
            store.set_metadata(slug, got, "wikipedia")
            row = store.get_metadata(slug)
    return {"slug": slug, **(row or _EMPTY)}


@router.put("/games/{slug}/metadata")
def put_metadata(slug: str, body: dict, device_id: str = Depends(_auth)) -> dict:
    """Manual entry; sticks until DELETEd."""
    _game_or_404(slug)
    store = _get_store()
    store.set_metadata(slug, body, "manual")
    return {"slug": slug, **store.get_metadata(slug)}


@router.delete("/games/{slug}/metadata")
def delete_metadata(slug: str, device_id: str = Depends(_auth)) -> dict:
    """Clear the cached/manual row; the next GET refetches."""
    _game_or_404(slug)
    _get_store().delete_metadata(slug)
    return {"ok": True}
