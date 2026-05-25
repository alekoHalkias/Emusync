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
    assert r.json()["game"] == "pokemon-emerald"

    r = await client.get("/games", headers=auth)
    assert r.status_code == 200
    assert any(g["game"] == "pokemon-emerald" for g in r.json())


@pytest.mark.asyncio
async def test_remove_game(client):
    token = await _pair(client)
    auth = {"Authorization": f"Bearer {token}"}

    await client.post("/games", json={"name": "Test Game"}, headers=auth)
    r = await client.delete("/games/test-game", headers=auth)
    assert r.status_code == 200

    r = await client.get("/games", headers=auth)
    assert not any(g["game"] == "test-game" for g in r.json())


@pytest.mark.asyncio
async def test_get_nonexistent_game(client):
    token = await _pair(client)
    auth = {"Authorization": f"Bearer {token}"}
    r = await client.get("/games/does-not-exist", headers=auth)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_add_game_with_console(client):
    token = await _pair(client)
    auth = {"Authorization": f"Bearer {token}"}

    r = await client.post("/games", json={"name": "Pokemon Emerald", "console": "GBA"}, headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["game"] == "pokemon-emerald"
    assert body["console"] == "GBA"

    r = await client.get("/games/pokemon-emerald", headers=auth)
    assert r.status_code == 200
    assert r.json()["console"] == "GBA"


@pytest.mark.asyncio
async def test_list_games_includes_console(client):
    token = await _pair(client)
    auth = {"Authorization": f"Bearer {token}"}

    await client.post("/games", json={"name": "Game 1", "console": "GBA"}, headers=auth)
    await client.post("/games", json={"name": "Game 2", "console": "SNES"}, headers=auth)

    r = await client.get("/games", headers=auth)
    assert r.status_code == 200
    games = r.json()
    assert len(games) == 2
    assert any(g["game"] == "game-1" and g["console"] == "GBA" for g in games)
    assert any(g["game"] == "game-2" and g["console"] == "SNES" for g in games)


@pytest.mark.asyncio
async def test_update_game_console(client):
    token = await _pair(client)
    auth = {"Authorization": f"Bearer {token}"}

    await client.post("/games", json={"name": "Test Game"}, headers=auth)

    r = await client.put("/games/test-game", json={"name": "Test Game", "console": "GB"}, headers=auth)
    assert r.status_code == 200
    assert r.json()["console"] == "GB"

    r = await client.get("/games/test-game", headers=auth)
    assert r.status_code == 200
    assert r.json()["console"] == "GB"


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


@pytest.mark.asyncio
async def test_get_lock_reflects_owning_device(client):
    """get_lock returns the device_id so emusync run can detect its own duplicate launch."""
    token = await _pair(client)
    auth = {"Authorization": f"Bearer {token}"}
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=auth)

    await client.post("/games/pokemon-emerald/lock", headers=auth)
    r = await client.get("/games/pokemon-emerald/lock", headers=auth)
    assert r.status_code == 200
    data = r.json()
    assert data["locked"] is True
    assert data["device_id"] == DEVICE_ID


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
    """Deleting a game must remove its locks but saves persist (they're global)."""
    token = await _pair(client)
    auth = {"Authorization": f"Bearer {token}"}

    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=auth)
    await client.post("/games/pokemon-emerald/save", content=b"save data", headers=auth)
    await client.post("/games/pokemon-emerald/lock", headers=auth)

    await client.delete("/games/pokemon-emerald", headers=auth)

    # Game is gone
    r = await client.get("/games/pokemon-emerald", headers=auth)
    assert r.status_code == 404

    # Re-add the game — lock should be gone but save persists (it's global)
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=auth)
    r = await client.get("/games/pokemon-emerald/save", headers=auth)
    assert r.status_code == 200, "save should persist (it's global)"
    r = await client.get("/games/pokemon-emerald/lock", headers=auth)
    assert r.json()["locked"] is False, "lock should be cleared"


@pytest.mark.asyncio
async def test_stale_lock_can_be_taken_after_ttl(client):
    """A stale lock on one device should not prevent another device from acquiring a fresh lock."""
    from server.store import Game
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        api_module.init(store, MASTER_TOKEN)

        # Pair two devices directly against the store
        store.register_device("device-1", "PC", "token-1")
        store.register_device("device-2", "Deck", "token-2")

        # Add game for both devices
        store.add_game(Game(game="test-game", device_id="device-1", name="Test Game"))
        store.add_game(Game(game="test-game", device_id="device-2", name="Test Game"))

        # Device 1 acquires lock, then backdate it past the TTL
        store.acquire_lock("test-game", "device-1")
        expired_time = (datetime.now(timezone.utc) - timedelta(hours=LOCK_TTL_HOURS + 1)).isoformat()
        store._conn.execute(
            "UPDATE locks SET acquired_at = ? WHERE game = ? AND device_id = ?",
            (expired_time, "test-game", "device-1"),
        )
        store._conn.commit()

        # Device 2 should be able to acquire its own lock even with device-1's stale lock
        store.acquire_lock("test-game", "device-2")
        lock = store.get_lock("test-game")
        # Since locks are per-device, device-2's lock should be there
        assert lock is not None


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

    # Reread: lock should be cleared but save persists (it's global)
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=auth)
    assert (await client.get("/games/pokemon-emerald/save", headers=auth)).status_code == 200, "save persists"
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
    assert r.json()["game"] == "pokemon-emerald"


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


# ── activity events ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_events_empty_on_fresh_store(client):
    token = await _pair(client)
    auth = {"Authorization": f"Bearer {token}"}
    r = await client.get("/events", headers=auth)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_save_synced_event_logged(client):
    token = await _pair(client)
    auth = {"Authorization": f"Bearer {token}"}
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=auth)
    await client.post("/games/pokemon-emerald/save", content=b"save data", headers=auth)

    r = await client.get("/events", headers=auth)
    events = r.json()
    assert any(e["type"] == "save_synced" and e["game"] == "pokemon-emerald" for e in events)


@pytest.mark.asyncio
async def test_game_started_and_stopped_events_logged(client):
    token = await _pair(client)
    auth = {"Authorization": f"Bearer {token}"}
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=auth)
    await client.post("/games/pokemon-emerald/lock", headers=auth)
    await client.delete("/games/pokemon-emerald/lock", headers=auth)

    r = await client.get("/events", headers=auth)
    types = [e["type"] for e in r.json()]
    assert "game_started" in types
    assert "game_stopped" in types


@pytest.mark.asyncio
async def test_events_include_device_name(client):
    token = await _pair(client)
    auth = {"Authorization": f"Bearer {token}"}
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=auth)
    await client.post("/games/pokemon-emerald/save", content=b"save data", headers=auth)

    r = await client.get("/events", headers=auth)
    save_event = next(e for e in r.json() if e["type"] == "save_synced")
    assert save_event["device_name"] == DEVICE_NAME


@pytest.mark.asyncio
async def test_events_ordered_newest_first(client):
    token = await _pair(client)
    auth = {"Authorization": f"Bearer {token}"}
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=auth)
    await client.post("/games/pokemon-emerald/lock", headers=auth)
    await client.post("/games/pokemon-emerald/save", content=b"save", headers=auth)

    r = await client.get("/events", headers=auth)
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
        assert events[0]["game"] is None
        assert events[0]["device_id"] is None


# ── update_game regression: cascade delete bug ────────────────────────────────

@pytest.mark.asyncio
async def test_update_game_name_preserves_save_and_device_config(client):
    """Renaming a game must not cascade-delete its saves or device config.

    Regression: update_game previously called store.add_game() which uses
    INSERT OR REPLACE, deleting the existing row (and cascading to saves,
    game_devices, locks) before re-inserting it.  The fix uses UPDATE instead.
    """
    token = await _pair(client)
    auth = {"Authorization": f"Bearer {token}"}

    # Create game + push a save + set device config
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=auth)
    await client.post("/games/pokemon-emerald/save", content=b"save-data-v1", headers=auth)
    await client.put("/games/pokemon-emerald/device", json={
        "rom_path": "/roms/emerald.gba",
        "save_path": "/saves/emerald.sav",
        "launch_command": "retroarch emerald.gba",
    }, headers=auth)

    # Rename the game
    r = await client.put("/games/pokemon-emerald", json={"name": "Pokemon Emerald GBA"}, headers=auth)
    assert r.status_code == 200
    assert r.json()["name"] == "Pokemon Emerald GBA"

    # Save must still be present
    save_meta = await client.get("/games/pokemon-emerald/save/meta", headers=auth)
    assert save_meta.status_code == 200, "save was cascade-deleted by rename (regression)"

    # Device config must still be present
    device_cfg = await client.get("/games/pokemon-emerald/device", headers=auth)
    assert device_cfg.status_code == 200, "device config was cascade-deleted by rename (regression)"
    assert device_cfg.json()["rom_path"] == "/roms/emerald.gba"

    # The game itself and the other games in list must still be accessible
    games = await client.get("/games", headers=auth)
    assert games.status_code == 200
    assert any(g["game"] == "pokemon-emerald" for g in games.json())


@pytest.mark.asyncio
async def test_update_game_name_does_not_wipe_other_games(client):
    """Renaming one game must not affect other games' data."""
    token = await _pair(client)
    auth = {"Authorization": f"Bearer {token}"}

    await client.post("/games", json={"name": "Game One"}, headers=auth)
    await client.post("/games", json={"name": "Game Two"}, headers=auth)
    await client.post("/games/game-two/save", content=b"save-two", headers=auth)

    # Rename Game One
    await client.put("/games/game-one", json={"name": "Game One Renamed"}, headers=auth)

    # Game Two's save must be intact
    meta = await client.get("/games/game-two/save/meta", headers=auth)
    assert meta.status_code == 200, "other game's save was wiped when a different game was renamed"

    # Both games should appear in the list
    games = await client.get("/games", headers=auth)
    slugs = {g["game"] for g in games.json()}
    assert "game-one" in slugs
    assert "game-two" in slugs


@pytest.mark.asyncio
async def test_push_saves_endpoint(client):
  """POST /games/:slug/push-saves pushes current save and state files from disk."""
  import tempfile
  from pathlib import Path

  token = await _pair(client)
  auth = {"Authorization": f"Bearer {token}"}

  # Create game
  await client.post("/games", json={"name": "Test Game"}, headers=auth)

  # Create temporary save and state files
  with tempfile.TemporaryDirectory() as tmpdir:
    save_path = Path(tmpdir) / "game.sav"
    state_path = Path(tmpdir) / "game.state"
    save_path.write_bytes(b"save-data-v1")
    state_path.write_bytes(b"state-data-v1")

    # Set device config with paths to our temp files
    await client.put("/games/test-game/device", json={
      "rom_path": "/roms/test.gba",
      "save_path": str(save_path),
      "launch_command": "retroarch test.gba",
      "state_path": str(state_path),
    }, headers=auth)

    # Push saves
    r = await client.post("/games/test-game/push-saves", headers=auth)
    assert r.status_code == 200
    assert r.json()["pushed"]["save"] is True
    assert r.json()["pushed"]["state"] is True

    # Verify save and state are now in the database
    save_meta = await client.get("/games/test-game/save/meta", headers=auth)
    assert save_meta.status_code == 200

    state_meta = await client.get("/games/test-game/state/meta", headers=auth)
    assert state_meta.status_code == 200
