"""
Integration tests for EmuSync — real SQLite DB, real FastAPI app, no mocks.

Run:  .venv/bin/python -m pytest tests/ -v
"""
from __future__ import annotations

import hashlib
import tempfile
from datetime import datetime, timezone, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from server import api as api_module
from server.store import Store, LOCK_TTL_HOURS

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


# ── store direct tests ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cascade_delete_removes_saves_and_locks(client):
    """Deleting a game must remove its saves and locks from the DB."""
    token = await _pair(client)
    auth = {"Authorization": f"Bearer {token}"}

    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=auth)
    await client.post("/games/pokemon-emerald/save", content=b"save data", headers=auth)
    await client.post("/games/pokemon-emerald/lock", headers=auth)

    await client.delete("/games/pokemon-emerald", headers=auth)

    # Game is gone
    r = await client.get("/games/pokemon-emerald", headers=auth)
    assert r.status_code == 404

    # Re-add the game — save and lock should not reappear
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=auth)
    r = await client.get("/games/pokemon-emerald/save", headers=auth)
    assert r.status_code == 204
    r = await client.get("/games/pokemon-emerald/lock", headers=auth)
    assert r.json()["locked"] is False


@pytest.mark.asyncio
async def test_stale_lock_can_be_taken_after_ttl(client):
    """A lock older than LOCK_TTL_HOURS should be claimable by another device."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        api_module.init(store, MASTER_TOKEN)

        # Pair two devices directly against the store
        store.register_device("device-1", "PC", "token-1")
        store.register_device("device-2", "Deck", "token-2")
        store.add_game("test-game", "Test Game")

        # Device 1 acquires lock, then backdate it past the TTL
        store.acquire_lock("test-game", "device-1")
        expired_time = (datetime.now(timezone.utc) - timedelta(hours=LOCK_TTL_HOURS + 1)).isoformat()
        store._conn.execute(
            "UPDATE locks SET acquired_at = ? WHERE game_slug = ?",
            (expired_time, "test-game"),
        )
        store._conn.commit()

        # Device 2 should now be able to take it
        store.acquire_lock("test-game", "device-2")
        lock = store.get_lock("test-game")
        assert lock is not None
        assert lock.device_id == "device-2"


@pytest.mark.asyncio
async def test_push_save_twice_keeps_only_latest(client):
    """Pushing a save twice must replace the first — only one row in the DB."""
    token = await _pair(client)
    auth = {"Authorization": f"Bearer {token}"}
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=auth)

    await client.post("/games/pokemon-emerald/save", content=b"version one", headers=auth)
    await client.post("/games/pokemon-emerald/save", content=b"version two", headers=auth)

    r = await client.get("/games/pokemon-emerald/save", headers=auth)
    assert r.content == b"version two"


# ── API edge cases ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_game_clears_lock_and_save(client):
    token = await _pair(client)
    auth = {"Authorization": f"Bearer {token}"}

    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=auth)
    await client.post("/games/pokemon-emerald/save", content=b"save", headers=auth)
    await client.post("/games/pokemon-emerald/lock", headers=auth)

    r = await client.delete("/games/pokemon-emerald", headers=auth)
    assert r.status_code == 200

    # Neither save nor lock endpoint should find anything
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=auth)
    assert (await client.get("/games/pokemon-emerald/save", headers=auth)).status_code == 204
    assert (await client.get("/games/pokemon-emerald/lock", headers=auth)).json()["locked"] is False


@pytest.mark.asyncio
async def test_set_device_config_nonexistent_game(client):
    """PUT /games/:slug/device on a slug that doesn't exist should 404 or fail gracefully."""
    token = await _pair(client)
    auth = {"Authorization": f"Bearer {token}"}

    r = await client.put("/games/ghost-game/device", json={
        "rom_path": "/roms/ghost.gba",
        "save_path": "/roms/ghost.srm",
        "launch_command": "retroarch ghost.gba",
    }, headers=auth)
    # Should not silently succeed — foreign key constraint on game_slug
    assert r.status_code in (404, 422, 500)


@pytest.mark.asyncio
async def test_save_meta_returns_204_when_no_save(client):
    token = await _pair(client)
    auth = {"Authorization": f"Bearer {token}"}
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=auth)

    r = await client.get("/games/pokemon-emerald/save/meta", headers=auth)
    assert r.status_code == 204


# ── two-device save sync ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_two_device_save_sync(client):
    """Device A pushes v1, device B pulls and verifies, B pushes v2, A pulls and gets v2."""
    # Pair device A
    r = await client.post("/pair", json={
        "master_token": MASTER_TOKEN,
        "device_id": "device-a",
        "device_name": "Gaming PC",
    })
    token_a = r.json()["token"]
    auth_a = {"Authorization": f"Bearer {token_a}"}

    # Pair device B
    r = await client.post("/pair", json={
        "master_token": MASTER_TOKEN,
        "device_id": "device-b",
        "device_name": "Steam Deck",
    })
    token_b = r.json()["token"]
    auth_b = {"Authorization": f"Bearer {token_b}"}

    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=auth_a)

    # Device A pushes v1
    save_v1 = b"save file version 1 - just started game"
    r = await client.post("/games/pokemon-emerald/save", content=save_v1, headers=auth_a)
    hash_v1 = r.json()["hash"]
    assert hash_v1 == hashlib.sha256(save_v1).hexdigest()

    # Device B pulls and verifies hash matches
    r = await client.get("/games/pokemon-emerald/save", headers=auth_b)
    assert r.status_code == 200
    assert r.content == save_v1
    assert r.headers["x-save-hash"] == hash_v1

    # Device B pushes v2
    save_v2 = b"save file version 2 - beat first gym"
    r = await client.post("/games/pokemon-emerald/save", content=save_v2, headers=auth_b)
    hash_v2 = r.json()["hash"]
    assert hash_v2 == hashlib.sha256(save_v2).hexdigest()
    assert hash_v2 != hash_v1

    # Device A pulls and gets v2
    r = await client.get("/games/pokemon-emerald/save", headers=auth_a)
    assert r.content == save_v2
    assert r.headers["x-save-hash"] == hash_v2


# ── blank PIN (open access) ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pair_with_blank_pin_succeeds():
    """When server_pin is blank any device can pair without a code."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        api_module.init(store, "")  # blank master token = open access
        async with AsyncClient(
            transport=ASGITransport(app=api_module.app),
            base_url="http://test",
        ) as c:
            r = await c.post("/pair", json={
                "master_token": "",
                "device_id": "open-device",
                "device_name": "Open Device",
            })
            assert r.status_code == 200
            assert r.json()["token"]


@pytest.mark.asyncio
async def test_pair_with_blank_pin_ignores_wrong_code():
    """Blank server PIN means even a wrong code is accepted."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        api_module.init(store, "")
        async with AsyncClient(
            transport=ASGITransport(app=api_module.app),
            base_url="http://test",
        ) as c:
            r = await c.post("/pair", json={
                "master_token": "some-random-garbage",
                "device_id": "open-device",
                "device_name": "Open Device",
            })
            assert r.status_code == 200


# ── devices endpoint ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_devices(client):
    token = await _pair(client)
    auth = {"Authorization": f"Bearer {token}"}

    r = await client.get("/devices", headers=auth)
    assert r.status_code == 200
    devices = r.json()
    assert any(d["id"] == DEVICE_ID for d in devices)
    assert any(d["name"] == DEVICE_NAME for d in devices)


@pytest.mark.asyncio
async def test_list_devices_shows_all_paired(client):
    r1 = await client.post("/pair", json={"master_token": MASTER_TOKEN, "device_id": "d1", "device_name": "PC"})
    r2 = await client.post("/pair", json={"master_token": MASTER_TOKEN, "device_id": "d2", "device_name": "Deck"})
    auth = {"Authorization": f"Bearer {r1.json()['token']}"}

    r = await client.get("/devices", headers=auth)
    ids = [d["id"] for d in r.json()]
    assert "d1" in ids
    assert "d2" in ids


# ── game rename ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_game_name(client):
    token = await _pair(client)
    auth = {"Authorization": f"Bearer {token}"}

    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=auth)

    r = await client.put("/games/pokemon-emerald", json={"name": "Pokemon Emerald v2"}, headers=auth)
    assert r.status_code == 200
    assert r.json()["name"] == "Pokemon Emerald v2"
    assert r.json()["slug"] == "pokemon-emerald"


@pytest.mark.asyncio
async def test_update_nonexistent_game_returns_404(client):
    token = await _pair(client)
    auth = {"Authorization": f"Bearer {token}"}

    r = await client.put("/games/ghost-game", json={"name": "Ghost"}, headers=auth)
    assert r.status_code == 404


# ── clear_devices ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_clear_devices_removes_all(client):
    await client.post("/pair", json={"master_token": MASTER_TOKEN, "device_id": "d1", "device_name": "PC"})
    r2 = await client.post("/pair", json={"master_token": MASTER_TOKEN, "device_id": "d2", "device_name": "Deck"})
    auth = {"Authorization": f"Bearer {r2.json()['token']}"}

    r = await client.get("/devices", headers=auth)
    assert len(r.json()) == 2

    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        store.register_device("d1", "PC", "tok1")
        store.register_device("d2", "Deck", "tok2")
        assert len(store.list_devices()) == 2
        store.clear_devices()
        assert store.list_devices() == []


# ── pair idempotency ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pair_same_device_id_updates_token(client):
    """Pairing the same device_id twice issues a new token, not a duplicate row."""
    r1 = await client.post("/pair", json={"master_token": MASTER_TOKEN, "device_id": DEVICE_ID, "device_name": DEVICE_NAME})
    r2 = await client.post("/pair", json={"master_token": MASTER_TOKEN, "device_id": DEVICE_ID, "device_name": DEVICE_NAME})
    token1 = r1.json()["token"]
    token2 = r2.json()["token"]

    # New token issued each time
    assert token1 != token2

    # Old token should no longer be valid
    r = await client.get("/games", headers={"Authorization": f"Bearer {token1}"})
    assert r.status_code == 401

    # New token works
    r = await client.get("/games", headers={"Authorization": f"Bearer {token2}"})
    assert r.status_code == 200
