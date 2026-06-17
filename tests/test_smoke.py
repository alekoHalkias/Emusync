"""End-to-end smoke flow and the batched /games/overview endpoint (#202)."""
from __future__ import annotations

import hashlib

import pytest

from tests.conftest import AUTH, DEVICE_ID


# ── schema smoke test ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_flow(client):
    """Smoke test: connect → add game → push save → verify hash → lock → unlock."""
    await client.post("/games", json={"name": "Metroid Fusion"}, headers=AUTH)
    await client.put("/games/metroid-fusion/device", json={
        "rom_path": "/roms/fusion.gba",
        "save_path": "/roms/fusion.srm",
        "launch_command": "retroarch -L mgba.so /roms/fusion.gba",
    }, headers=AUTH)

    save = b"\xDE\xAD\xBE\xEF" * 512
    r = await client.post("/games/metroid-fusion/save", content=save, headers=AUTH)
    assert r.json()["hash"] == hashlib.sha256(save).hexdigest()

    r = await client.get("/games/metroid-fusion/save", headers=AUTH)
    assert r.content == save

    await client.post("/games/metroid-fusion/lock", headers=AUTH)
    r = await client.get("/games/metroid-fusion/lock", headers=AUTH)
    assert r.json()["locked"] is True

    await client.delete("/games/metroid-fusion/lock", headers=AUTH)
    r = await client.get("/games/metroid-fusion/lock", headers=AUTH)
    assert r.json()["locked"] is False


# ── games overview batch endpoint (#202) ───────────────────────────────────────

@pytest.mark.asyncio
async def test_games_overview_batches_lock_save_and_config(client):
    """One call returns each game's lock + last save + this device's config."""
    await client.post("/games", json={"name": "Metroid", "console": "GBA"}, headers=AUTH)
    await client.post("/games", json={"name": "Zelda", "console": "GBA"}, headers=AUTH)
    # Configure + lock + push a save for Metroid only
    await client.put(
        "/games/metroid/device",
        json={"rom_path": "/roms/metroid.gba", "save_path": "/saves/metroid.srm"},
        headers=AUTH,
    )
    await client.post("/games/metroid/lock", headers=AUTH)
    await client.post("/games/metroid/save", content=b"savedata", headers=AUTH)

    r = await client.get("/games/overview", headers=AUTH)
    assert r.status_code == 200
    overview = {g["slug"]: g for g in r.json()}

    assert overview["metroid"]["locked"] is True
    assert overview["metroid"]["lock_device_id"] == DEVICE_ID
    assert overview["metroid"]["is_local"] is True
    assert overview["metroid"]["rom_path"] == "/roms/metroid.gba"
    assert overview["metroid"]["last_push"] is not None

    # Zelda has no config / lock / save
    assert overview["zelda"]["locked"] is False
    assert overview["zelda"]["is_local"] is False
    assert overview["zelda"]["last_push"] is None


@pytest.mark.asyncio
async def test_games_overview_route_not_shadowed_by_slug(client):
    """GET /games/overview must hit the overview route, not get_game('overview')."""
    r = await client.get("/games/overview", headers=AUTH)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
