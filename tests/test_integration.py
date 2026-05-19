"""
Integration tests for EmuSync — real SQLite DB, real FastAPI app, no mocks.

Run:  .venv/bin/python -m pytest tests/ -v
"""
from __future__ import annotations

import hashlib
import tempfile

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from server import api as api_module
from server.store import Store

MASTER_TOKEN = "test-master-token"
DEVICE_ID = "device-abc"
DEVICE_NAME = "test-pc"


@pytest_asyncio.fixture
async def client():
    """Fresh in-memory store + FastAPI app for each test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        api_module.init(store, MASTER_TOKEN)
        async with AsyncClient(
            transport=ASGITransport(app=api_module.app),
            base_url="http://test",
        ) as c:
            yield c


async def _pair(client: AsyncClient) -> str:
    """Pair a device and return its bearer token."""
    r = await client.post("/pair", json={
        "master_token": MASTER_TOKEN,
        "device_id": DEVICE_ID,
        "device_name": DEVICE_NAME,
    })
    assert r.status_code == 200
    return r.json()["token"]


# ── health ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ── pairing ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pair_success(client):
    token = await _pair(client)
    assert isinstance(token, str) and len(token) > 0


@pytest.mark.asyncio
async def test_pair_wrong_master_token(client):
    r = await client.post("/pair", json={
        "master_token": "wrong",
        "device_id": DEVICE_ID,
        "device_name": DEVICE_NAME,
    })
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_auth_required(client):
    r = await client.get("/games")
    assert r.status_code == 401


# ── games ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_and_list_games(client):
    token = await _pair(client)
    auth = {"Authorization": f"Bearer {token}"}

    r = await client.post("/games", json={"name": "Pokemon Emerald"}, headers=auth)
    assert r.status_code == 200
    assert r.json()["slug"] == "pokemon-emerald"

    r = await client.get("/games", headers=auth)
    assert r.status_code == 200
    assert any(g["slug"] == "pokemon-emerald" for g in r.json())


@pytest.mark.asyncio
async def test_remove_game(client):
    token = await _pair(client)
    auth = {"Authorization": f"Bearer {token}"}

    await client.post("/games", json={"name": "Test Game"}, headers=auth)
    r = await client.delete("/games/test-game", headers=auth)
    assert r.status_code == 200

    r = await client.get("/games", headers=auth)
    assert not any(g["slug"] == "test-game" for g in r.json())


@pytest.mark.asyncio
async def test_get_nonexistent_game(client):
    token = await _pair(client)
    auth = {"Authorization": f"Bearer {token}"}
    r = await client.get("/games/does-not-exist", headers=auth)
    assert r.status_code == 404


# ── game device config ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_set_and_get_device_config(client):
    token = await _pair(client)
    auth = {"Authorization": f"Bearer {token}"}
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=auth)

    cfg = {
        "rom_path": "/roms/emerald.gba",
        "save_path": "/roms/emerald.srm",
        "launch_command": "retroarch -L mgba.so /roms/emerald.gba",
    }
    r = await client.put("/games/pokemon-emerald/device", json=cfg, headers=auth)
    assert r.status_code == 200

    r = await client.get("/games/pokemon-emerald/device", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["rom_path"] == cfg["rom_path"]
    assert body["save_path"] == cfg["save_path"]
    assert body["launch_command"] == cfg["launch_command"]


# ── save push / pull ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_push_and_pull_save(client):
    token = await _pair(client)
    auth = {"Authorization": f"Bearer {token}"}
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=auth)

    save_v1 = b"\x00\x01\x02\x03" * 256
    r = await client.post("/games/pokemon-emerald/save", content=save_v1, headers=auth)
    assert r.status_code == 200
    pushed_hash = r.json()["hash"]
    assert pushed_hash == hashlib.sha256(save_v1).hexdigest()

    r = await client.get("/games/pokemon-emerald/save", headers=auth)
    assert r.status_code == 200
    assert r.content == save_v1
    assert r.headers["x-save-hash"] == pushed_hash


@pytest.mark.asyncio
async def test_push_save_updates_version(client):
    token = await _pair(client)
    auth = {"Authorization": f"Bearer {token}"}
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=auth)

    save_v1 = b"save version 1"
    save_v2 = b"save version 2 with more progress"

    await client.post("/games/pokemon-emerald/save", content=save_v1, headers=auth)
    await client.post("/games/pokemon-emerald/save", content=save_v2, headers=auth)

    r = await client.get("/games/pokemon-emerald/save", headers=auth)
    assert r.content == save_v2
    assert r.headers["x-save-hash"] == hashlib.sha256(save_v2).hexdigest()


@pytest.mark.asyncio
async def test_pull_save_no_save_returns_204(client):
    token = await _pair(client)
    auth = {"Authorization": f"Bearer {token}"}
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=auth)

    r = await client.get("/games/pokemon-emerald/save", headers=auth)
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_save_meta(client):
    token = await _pair(client)
    auth = {"Authorization": f"Bearer {token}"}
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=auth)

    save_data = b"some save data"
    await client.post("/games/pokemon-emerald/save", content=save_data, headers=auth)

    r = await client.get("/games/pokemon-emerald/save/meta", headers=auth)
    assert r.status_code == 200
    meta = r.json()
    assert meta["hash"] == hashlib.sha256(save_data).hexdigest()
    assert "pushed_at" in meta


# ── locks ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_acquire_and_release_lock(client):
    token = await _pair(client)
    auth = {"Authorization": f"Bearer {token}"}
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=auth)

    r = await client.get("/games/pokemon-emerald/lock", headers=auth)
    assert r.json()["locked"] is False

    r = await client.post("/games/pokemon-emerald/lock", headers=auth)
    assert r.status_code == 200

    r = await client.get("/games/pokemon-emerald/lock", headers=auth)
    assert r.json()["locked"] is True

    r = await client.delete("/games/pokemon-emerald/lock", headers=auth)
    assert r.status_code == 200

    r = await client.get("/games/pokemon-emerald/lock", headers=auth)
    assert r.json()["locked"] is False


@pytest.mark.asyncio
async def test_second_device_cannot_acquire_held_lock(client):
    """Two different devices — second one must be rejected while first holds the lock."""
    # Pair device 1
    r = await client.post("/pair", json={
        "master_token": MASTER_TOKEN,
        "device_id": "device-1",
        "device_name": "PC",
    })
    token1 = r.json()["token"]
    auth1 = {"Authorization": f"Bearer {token1}"}

    # Pair device 2
    r = await client.post("/pair", json={
        "master_token": MASTER_TOKEN,
        "device_id": "device-2",
        "device_name": "Steam Deck",
    })
    token2 = r.json()["token"]
    auth2 = {"Authorization": f"Bearer {token2}"}

    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=auth1)

    # Device 1 acquires lock
    r = await client.post("/games/pokemon-emerald/lock", headers=auth1)
    assert r.status_code == 200

    # Device 2 should be rejected
    r = await client.post("/games/pokemon-emerald/lock", headers=auth2)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_same_device_can_reacquire_own_lock(client):
    token = await _pair(client)
    auth = {"Authorization": f"Bearer {token}"}
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=auth)

    await client.post("/games/pokemon-emerald/lock", headers=auth)
    r = await client.post("/games/pokemon-emerald/lock", headers=auth)
    assert r.status_code == 200


# ── schema smoke test ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_flow(client):
    """Smoke test: pair → add game → push save → verify hash → lock → unlock."""
    token = await _pair(client)
    auth = {"Authorization": f"Bearer {token}"}

    await client.post("/games", json={"name": "Metroid Fusion"}, headers=auth)
    await client.put("/games/metroid-fusion/device", json={
        "rom_path": "/roms/fusion.gba",
        "save_path": "/roms/fusion.srm",
        "launch_command": "retroarch -L mgba.so /roms/fusion.gba",
    }, headers=auth)

    save = b"\xDE\xAD\xBE\xEF" * 512
    r = await client.post("/games/metroid-fusion/save", content=save, headers=auth)
    assert r.json()["hash"] == hashlib.sha256(save).hexdigest()

    r = await client.get("/games/metroid-fusion/save", headers=auth)
    assert r.content == save

    await client.post("/games/metroid-fusion/lock", headers=auth)
    r = await client.get("/games/metroid-fusion/lock", headers=auth)
    assert r.json()["locked"] is True

    await client.delete("/games/metroid-fusion/lock", headers=auth)
    r = await client.get("/games/metroid-fusion/lock", headers=auth)
    assert r.json()["locked"] is False
