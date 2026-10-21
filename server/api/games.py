"""Games endpoints: CRUD + overview + IGDB metadata."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger("emusync.api")

from ..store import Game
from ._core import _game_label, _get_store, _auth
from .defs import slug_param_dep
from .igdb import fetch_igdb_metadata as get_igdb_metadata

router = APIRouter()


class GameResponse(BaseModel):
    """Games list endpoint response (issue #578)."""
    slug: str
    name: str
    console: Optional[str]
    sgdb_game_id: Optional[int]
    switch_title_id: Optional[str]
    igdb_slug: Optional[str] = Field(None, description="SteamGridDB game ID if set")


class GameDetails(BaseModel):
    """Game details endpoint response."""
    slug: str
    name: str
    console: Optional[str]
    sgdb_game_id: Optional[int]
    switch_title_id: Optional[str]
    igdb: Optional[dict] = Field(None, description="IGDB metadata (title, synopsis, cover art)")


@router.post("/games")
async def add_game(request: Request, body: dict) -> GameResponse:
    """Create a new game."""
    store = _get_store()
    name = body.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    game = store.add_game(name)
    return GameResponse(**game.model_dump(exclude_none=True))

@router.get("/games/overview")
async def list_games(
    request: Request,
) -> list[GameResponse]:
    """List all games with their IGDB slug if available."""
    store = _get_store()
    games_list = store.list_games()

    return [
        GameResponse(**game.model_dump(exclude_none=True))
        for game in games_list
    ]


@router.get("/games/{slug}")
async def get_game(
    slug: str,
    request: Request,
) -> GameDetails:
    """Get a single game with IGDB metadata if fetched."""
    store = _get_store()
    game = store.get_game(slug)

    if not game:
        raise HTTPException(status_code=404, detail=f"Game '{slug}' not found")

    # Fetch IGDB metadata via dependency (issue #578)
    igdb_meta = await get_igdb_metadata(game.name)
    if igdb_meta:
        return GameDetails(**game.model_dump(exclude_none=True), igdb=igdb_meta)
    return GameDetails(**game.model_dump(exclude_none=True))


@router.get("/games/{slug}/metadata")
async def get_game_metadata(
    slug: str,
    request: Request,
    device_id: Optional[str] = Depends(slug_param_dep),
    force_fetch: bool = False,
) -> dict:
    """Get only IGDB metadata for a game (issue #578).

    - `device_id`: Used to validate ownership (only devices that own this game
      can fetch its metadata; prevents cross-device scraping).
    - `force_fetch`: When true, bypass the Store's cached metadata and refetch
      from IGDB. On false (default), reuse whatever the Store has cached for
      the game's slug/name pair.
    """
    store = _get_store()
    # Validate game existence
    game = store.get_game(slug)
    if not game:
        raise HTTPException(status_code=404, detail=f"Game '{slug}' not found")

    meta = store.get_game_metadata(game)

    if meta is None:
        from ..config import load
        auto_fetch = load().auto_fetch_metadata
        if auto_fetch:
            logger.debug("Fetching IGDB metadata for '%s'...", slug)
            result = await get_igdb_metadata(game.name)
            if result:
                store.set_game_metadata(game, result)
                meta = {"slug": game.slug, **result}

    if meta is None:
        if force_fetch:
            raise HTTPException(status_code=404, detail=f"IGDB metadata for '{slug}' not available")
        return {"slug": slug, "name": game.name, "cover": None, "synopsis": ""}

    return meta
