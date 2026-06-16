"""Activity event logging tests."""
from __future__ import annotations

import tempfile

import pytest

from server.store import Store
from tests.conftest import AUTH, DEVICE_ID, DEVICE_NAME


@pytest.mark.asyncio
async def test_events_empty_on_fresh_store(client):
    r = await client.get("/events", headers=AUTH)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_save_synced_event_logged(client):
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=AUTH)
    await client.post("/games/pokemon-emerald/save", content=b"save data", headers=AUTH)

    r = await client.get("/events", headers=AUTH)
    events = r.json()
    assert any(e["type"] == "save_synced" and e["game_slug"] == "pokemon-emerald" for e in events)


@pytest.mark.asyncio
async def test_game_started_and_stopped_events_logged(client):
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=AUTH)
    await client.post("/games/pokemon-emerald/lock", headers=AUTH)
    await client.delete("/games/pokemon-emerald/lock", headers=AUTH)

    r = await client.get("/events", headers=AUTH)
    types = [e["type"] for e in r.json()]
    assert "game_started" in types
    assert "game_stopped" in types


@pytest.mark.asyncio
async def test_events_include_device_name(client):
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=AUTH)
    await client.post("/games/pokemon-emerald/save", content=b"save data", headers=AUTH)

    r = await client.get("/events", headers=AUTH)
    save_event = next(e for e in r.json() if e["type"] == "save_synced")
    assert save_event["device_name"] == DEVICE_NAME


@pytest.mark.asyncio
async def test_events_ordered_newest_first(client):
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=AUTH)
    await client.post("/games/pokemon-emerald/lock", headers=AUTH)
    await client.post("/games/pokemon-emerald/save", content=b"save", headers=AUTH)

    r = await client.get("/events", headers=AUTH)
    events = r.json()
    assert events[0]["type"] == "save_synced"
    assert events[1]["type"] == "game_started"


@pytest.mark.asyncio
async def test_events_requires_auth(client):
    r = await client.get("/events")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_log_event_server_started_direct():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        store.log_event("server_started")
        events = store.list_events()
        assert len(events) == 1
        assert events[0]["type"] == "server_started"
        assert events[0]["game_slug"] is None
        assert events[0]["device_id"] is None


@pytest.mark.asyncio
async def test_game_added_event_logged(client):
    """When a game is imported with a rom_path, a game_added event is logged with rom_path."""
    await client.post("/games", json={"name": "Zelda - A Link to the Past", "console": "SNES"}, headers=AUTH)
    rom_path = "/home/user/Games/SNES/zelda3.smc"
    await client.put("/games/zelda-a-link-to-the-past/device", json={
        "rom_path": rom_path,
        "save_path": "/saves/zelda3.sav",
        "launch_command": "retroarch zelda3.smc",
    }, headers=AUTH)

    r = await client.get("/events", headers=AUTH)
    assert r.status_code == 200
    events = r.json()
    game_added = next((e for e in events if e["type"] == "game_added"), None)
    assert game_added is not None, "game_added event not found"
    assert game_added["game_slug"] == "zelda-a-link-to-the-past"
    assert game_added["device_id"] == DEVICE_ID
    assert game_added["rom_path"] == rom_path


@pytest.mark.asyncio
async def test_game_added_event_only_when_rom_path(client):
    """game_added event should only fire if rom_path is non-empty."""
    await client.post("/games", json={"name": "Test Game"}, headers=AUTH)
    # Set device config with empty rom_path
    await client.put("/games/test-game/device", json={
        "rom_path": "",
        "save_path": "/saves/test.sav",
        "launch_command": "emulator test.rom",
    }, headers=AUTH)

    r = await client.get("/events", headers=AUTH)
    assert r.status_code == 200
    events = r.json()
    game_added = next((e for e in events if e["type"] == "game_added"), None)
    assert game_added is None, "game_added event should not fire for empty rom_path"
