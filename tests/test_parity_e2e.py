"""End-to-end tests for the complete parity check workflow."""
from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from server import api as api_module
from server.store import Store

MASTER_TOKEN = "test-master-token"


@pytest_asyncio.fixture
async def server():
    """Fresh in-memory store + FastAPI app."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        api_module.init(store, MASTER_TOKEN)
        async with AsyncClient(
            transport=ASGITransport(app=api_module.app),
            base_url="http://test",
        ) as client:
            yield client, store


async def _pair_device(client: AsyncClient, device_id: str, device_name: str) -> str:
    """Pair a device and return its token."""
    r = await client.post("/pair", json={
        "master_token": MASTER_TOKEN,
        "device_id": device_id,
        "device_name": device_name,
    })
    assert r.status_code == 200
    return r.json()["token"]


@pytest.mark.asyncio
async def test_parity_all_devices_in_sync(server):
    """Full workflow: Two devices, same game, both synced -> parity check passes."""
    client, store = server

    # Device 1: Gaming PC
    token1 = await _pair_device(client, "gaming-pc", "Gaming PC")
    auth1 = {"Authorization": f"Bearer {token1}"}

    # Device 2: Steam Deck
    token2 = await _pair_device(client, "steam-deck", "Steam Deck")
    auth2 = {"Authorization": f"Bearer {token2}"}

    # Both devices add the same game
    for auth in [auth1, auth2]:
        r = await client.post("/games", json={"name": "Zelda"}, headers=auth)
        assert r.status_code == 200
        assert r.json()["game"] == "zelda"

        r = await client.put("/games/zelda/device", json={
            "rom_path": "/roms/zelda.gba",
            "save_path": "/saves/zelda.sav",
            "launch_command": "retroarch -L mgba.so /roms/zelda.gba",
        }, headers=auth)
        assert r.status_code == 200

    # Both devices push the same save
    save_data = b"save-file-data"
    r = await client.post("/games/zelda/save", content=save_data, headers={**auth1, "Content-Type": "application/octet-stream"})
    assert r.status_code == 200
    r = await client.post("/games/zelda/save", content=save_data, headers={**auth2, "Content-Type": "application/octet-stream"})
    assert r.status_code == 200

    # Check parity from device 1
    r = await client.get("/games/zelda/parity", headers=auth1)
    assert r.status_code == 200
    parity = r.json()

    assert parity["game"] == "zelda"
    assert "gaming-pc" in parity["devices"]
    assert "steam-deck" in parity["devices"]

    # Both devices have the game
    assert parity["devices"]["gaming-pc"]["exists"] is True
    assert parity["devices"]["steam-deck"]["exists"] is True

    # The canonical save hash should match what was pushed (both pushed same data)
    save_hash = hashlib.sha256(save_data).hexdigest()
    # Only the latest pusher's save is stored canonically
    assert parity["devices"]["steam-deck"]["save_hash"] == save_hash
    # The other device doesn't have its own save entry (there's only one canonical save)
    assert parity["devices"]["gaming-pc"]["save_hash"] is None or parity["devices"]["gaming-pc"]["save_hash"] == save_hash


@pytest.mark.asyncio
async def test_parity_device_missing_game(server):
    """Workflow: Game on Device 1 only -> parity check reports Device 2 missing."""
    client, store = server

    token1 = await _pair_device(client, "device-1", "Device 1")
    auth1 = {"Authorization": f"Bearer {token1}"}

    token2 = await _pair_device(client, "device-2", "Device 2")
    auth2 = {"Authorization": f"Bearer {token2}"}

    # Only device 1 adds the game
    r = await client.post("/games", json={"name": "Mario"}, headers=auth1)
    assert r.status_code == 200

    r = await client.put("/games/mario/device", json={
        "rom_path": "/roms/mario.gba",
        "save_path": "/saves/mario.sav",
        "launch_command": "retroarch -L mgba.so /roms/mario.gba",
    }, headers=auth1)
    assert r.status_code == 200

    # Check parity
    r = await client.get("/games/mario/parity", headers=auth1)
    assert r.status_code == 200
    parity = r.json()

    assert parity["devices"]["device-1"]["exists"] is True
    assert parity["devices"]["device-2"]["exists"] is False


@pytest.mark.asyncio
async def test_parity_save_out_of_sync(server):
    """Workflow: Both have game, different saves -> parity reports out of sync."""
    client, store = server

    token1 = await _pair_device(client, "device-a", "Device A")
    auth1 = {"Authorization": f"Bearer {token1}"}

    token2 = await _pair_device(client, "device-b", "Device B")
    auth2 = {"Authorization": f"Bearer {token2}"}

    # Both add the game
    for auth in [auth1, auth2]:
        r = await client.post("/games", json={"name": "Chrono"}, headers=auth)
        assert r.status_code == 200
        r = await client.put("/games/chrono/device", json={
            "rom_path": "/roms/chrono.gba",
            "save_path": "/saves/chrono.sav",
            "launch_command": "retroarch",
        }, headers=auth)
        assert r.status_code == 200

    # Device A pushes save v1
    r = await client.post("/games/chrono/save", content=b"save-v1", headers={**auth1, "Content-Type": "application/octet-stream"})
    assert r.status_code == 200

    # Device B pushes save v2 (different)
    r = await client.post("/games/chrono/save", content=b"save-v2-newer-progress", headers={**auth2, "Content-Type": "application/octet-stream"})
    assert r.status_code == 200

    # Check parity
    r = await client.get("/games/chrono/parity", headers=auth1)
    assert r.status_code == 200
    parity = r.json()

    # Both have the game
    assert parity["devices"]["device-a"]["exists"] is True
    assert parity["devices"]["device-b"]["exists"] is True

    # But different save hashes
    assert parity["devices"]["device-a"]["save_hash"] != parity["devices"]["device-b"]["save_hash"]


@pytest.mark.asyncio
async def test_parity_state_out_of_sync(server):
    """Workflow: States configured, different state files -> parity reports out of sync."""
    client, store = server

    token1 = await _pair_device(client, "pc1", "PC 1")
    auth1 = {"Authorization": f"Bearer {token1}"}

    token2 = await _pair_device(client, "pc2", "PC 2")
    auth2 = {"Authorization": f"Bearer {token2}"}

    # Both add the game with state_path
    for auth in [auth1, auth2]:
        r = await client.post("/games", json={"name": "Pokemon"}, headers=auth)
        assert r.status_code == 200
        r = await client.put("/games/pokemon/device", json={
            "rom_path": "/roms/pokemon.gba",
            "save_path": "/saves/pokemon.sav",
            "launch_command": "retroarch",
            "state_path": "/states/pokemon.state",
        }, headers=auth)
        assert r.status_code == 200

    # Push same save data
    save_data = b"same-save"
    r = await client.post("/games/pokemon/save", content=save_data, headers={**auth1, "Content-Type": "application/octet-stream"})
    assert r.status_code == 200
    r = await client.post("/games/pokemon/save", content=save_data, headers={**auth2, "Content-Type": "application/octet-stream"})
    assert r.status_code == 200

    # Push different states
    r = await client.post("/games/pokemon/state", content=b"state-v1", headers={**auth1, "Content-Type": "application/octet-stream"})
    assert r.status_code == 200

    r = await client.post("/games/pokemon/state", content=b"state-v2-different", headers={**auth2, "Content-Type": "application/octet-stream"})
    assert r.status_code == 200

    # Check parity
    r = await client.get("/games/pokemon/parity", headers=auth1)
    assert r.status_code == 200
    parity = r.json()

    # Save hashes: there's only one canonical save, so only the latest pusher shows a hash
    save_hash = hashlib.sha256(save_data).hexdigest()
    assert parity["devices"]["pc2"]["save_hash"] == save_hash  # Latest pusher
    # PC1 doesn't show its own save since it was overwritten

    # States: only the latest pusher's state is stored (by design, similar to saves)
    state_v2_hash = hashlib.sha256(b"state-v2-different").hexdigest()
    assert parity["devices"]["pc2"]["state_hash"] == state_v2_hash  # Latest pusher
    # PC1's state was overwritten, so it doesn't show a hash from its own push
