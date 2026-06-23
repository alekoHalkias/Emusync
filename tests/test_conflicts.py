"""Save-conflict records behind the GUI Conflicts panel (issue #243)."""
from __future__ import annotations

import pytest

from tests.conftest import AUTH, _device_auth


def _report(client, slug, **kw):
    body = {"winner_device_id": "", "loser_device_id": "", "winner_hash": "", "loser_hash": "", **kw}
    return client.post(f"/games/{slug}/conflicts", json=body, headers=AUTH)


@pytest.mark.asyncio
async def test_report_lists_and_dismiss_conflict(client):
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=AUTH)

    r = await _report(client, "pokemon-emerald",
                      winner_device_id="dev-a", loser_device_id="dev-b",
                      winner_hash="h-win", loser_hash="h-lose")
    assert r.status_code == 200
    conflict_id = r.json()["id"]

    listed = (await client.get("/conflicts", headers=AUTH)).json()
    assert len(listed) == 1
    c = listed[0]
    assert c["game_slug"] == "pokemon-emerald"
    assert c["game_name"] == "Pokemon Emerald"
    assert c["loser_hash"] == "h-lose"

    # Dismiss removes it from the open list.
    r = await client.post(f"/conflicts/{conflict_id}/dismiss", headers=AUTH)
    assert r.status_code == 200
    assert (await client.get("/conflicts", headers=AUTH)).json() == []


@pytest.mark.asyncio
async def test_report_conflict_unknown_game_404(client):
    r = await _report(client, "no-such-game")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_dismiss_unknown_conflict_404(client):
    r = await client.post("/conflicts/nope/dismiss", headers=AUTH)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_duplicate_report_is_deduped(client):
    await client.post("/games", json={"name": "Zelda"}, headers=AUTH)
    r1 = await _report(client, "zelda", winner_hash="w", loser_hash="l")
    r2 = await _report(client, "zelda", winner_hash="w", loser_hash="l")
    # Same winner/loser hashes while still open → one row, same id.
    assert r1.json()["id"] == r2.json()["id"]
    assert len((await client.get("/conflicts", headers=AUTH)).json()) == 1


@pytest.mark.asyncio
async def test_conflict_resolves_device_names(client):
    """list_open_conflicts joins device names so the panel can show them."""
    auth_a = _device_auth("dev-a", "Steam Deck")
    auth_b = _device_auth("dev-b", "Gaming PC")
    # Register both devices via an authed request.
    await client.get("/health")
    await client.get("/games", headers=auth_a)
    await client.get("/games", headers=auth_b)
    await client.post("/games", json={"name": "Metroid"}, headers=auth_a)

    await _report(client, "metroid", winner_device_id="dev-a", loser_device_id="dev-b")
    c = (await client.get("/conflicts", headers=AUTH)).json()[0]
    assert c["winner_device_name"] == "Steam Deck"
    assert c["loser_device_name"] == "Gaming PC"


@pytest.mark.asyncio
async def test_removing_game_cascades_conflicts(client):
    await client.post("/games", json={"name": "Zelda"}, headers=AUTH)
    await _report(client, "zelda", winner_hash="w", loser_hash="l")
    assert len((await client.get("/conflicts", headers=AUTH)).json()) == 1
    await client.delete("/games/zelda", headers=AUTH)
    assert (await client.get("/conflicts", headers=AUTH)).json() == []
