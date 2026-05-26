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

MASTER_PIN = "test-master-pin"
DEVICE_ID = "device-abc"
DEVICE_NAME = "test-pc"

# Standard auth headers for the default test device
AUTH = {
    "Authorization": f"Bearer {MASTER_PIN}",
    "X-Device-ID": DEVICE_ID,
    "X-Device-Name": DEVICE_NAME,
}


def _device_auth(device_id: str, device_name: str, pin: str = MASTER_PIN) -> dict:
    """Build auth headers for a specific device."""
    return {
        "Authorization": f"Bearer {pin}",
        "X-Device-ID": device_id,
        "X-Device-Name": device_name,
    }


@pytest_asyncio.fixture
async def client():
    """Fresh in-memory store + FastAPI app for each test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        api_module.init(store, MASTER_PIN)
        async with AsyncClient(
            transport=ASGITransport(app=api_module.app),
            base_url="http://test",
        ) as c:
            yield c


# ── health ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ── authentication ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_auth_required(client):
    """Requests without headers should be rejected."""
    r = await client.get("/games")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_wrong_pin_rejected(client):
    """Wrong PIN should be rejected with 401."""
    bad_auth = _device_auth(DEVICE_ID, DEVICE_NAME, pin="wrong")
    r = await client.get("/games", headers=bad_auth)
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_missing_device_id_rejected(client):
    """Missing X-Device-ID header should be rejected."""
    r = await client.get("/games", headers={"Authorization": f"Bearer {MASTER_PIN}"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_device_auto_registered_on_first_request(client):
    """Devices should be auto-registered on first authenticated request — no explicit pair step."""
    r = await client.get("/games", headers=AUTH)
    assert r.status_code == 200

    r = await client.get("/devices", headers=AUTH)
    devices = r.json()
    assert any(d["id"] == DEVICE_ID for d in devices)
    assert any(d["name"] == DEVICE_NAME for d in devices)


# ── blank PIN (open access) ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_blank_pin_server_allows_any_device():
    """When server_pin is blank, any device connects without a code."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        api_module.init(store, "")  # blank = open access
        async with AsyncClient(
            transport=ASGITransport(app=api_module.app),
            base_url="http://test",
        ) as c:
            r = await c.get("/games", headers={"Authorization": "Bearer ", "X-Device-ID": "open-device", "X-Device-Name": "Open"})
            assert r.status_code == 200


@pytest.mark.asyncio
async def test_blank_pin_server_ignores_wrong_pin():
    """Blank server PIN accepts requests even with a non-empty PIN value."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        api_module.init(store, "")
        async with AsyncClient(
            transport=ASGITransport(app=api_module.app),
            base_url="http://test",
        ) as c:
            r = await c.get("/games", headers={"Authorization": "Bearer wrong-pin", "X-Device-ID": "d1", "X-Device-Name": "D1"})
            assert r.status_code == 200


# ── games ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_and_list_games(client):
    r = await client.post("/games", json={"name": "Pokemon Emerald"}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["slug"] == "pokemon-emerald"

    r = await client.get("/games", headers=AUTH)
    assert r.status_code == 200
    assert any(g["slug"] == "pokemon-emerald" for g in r.json())


@pytest.mark.asyncio
async def test_remove_game(client):
    await client.post("/games", json={"name": "Test Game"}, headers=AUTH)
    r = await client.delete("/games/test-game", headers=AUTH)
    assert r.status_code == 200

    r = await client.get("/games", headers=AUTH)
    assert not any(g["slug"] == "test-game" for g in r.json())


@pytest.mark.asyncio
async def test_get_nonexistent_game(client):
    r = await client.get("/games/does-not-exist", headers=AUTH)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_add_game_with_console(client):
    r = await client.post("/games", json={"name": "Pokemon Emerald", "console": "GBA"}, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["slug"] == "pokemon-emerald"
    assert body["console"] == "GBA"

    r = await client.get("/games/pokemon-emerald", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["console"] == "GBA"


@pytest.mark.asyncio
async def test_list_games_includes_console(client):
    await client.post("/games", json={"name": "Game 1", "console": "GBA"}, headers=AUTH)
    await client.post("/games", json={"name": "Game 2", "console": "SNES"}, headers=AUTH)

    r = await client.get("/games", headers=AUTH)
    assert r.status_code == 200
    games = r.json()
    assert len(games) == 2
    assert any(g["slug"] == "game-1" and g["console"] == "GBA" for g in games)
    assert any(g["slug"] == "game-2" and g["console"] == "SNES" for g in games)


@pytest.mark.asyncio
async def test_update_game_console(client):
    await client.post("/games", json={"name": "Test Game"}, headers=AUTH)

    r = await client.put("/games/test-game", json={"name": "Test Game", "console": "GB"}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["console"] == "GB"

    r = await client.get("/games/test-game", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["console"] == "GB"


# ── game device config ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_set_and_get_device_config(client):
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=AUTH)

    cfg = {
        "rom_path": "/roms/emerald.gba",
        "save_path": "/roms/emerald.srm",
        "launch_command": "retroarch -L mgba.so /roms/emerald.gba",
    }
    r = await client.put("/games/pokemon-emerald/device", json=cfg, headers=AUTH)
    assert r.status_code == 200

    r = await client.get("/games/pokemon-emerald/device", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["rom_path"] == cfg["rom_path"]
    assert body["save_path"] == cfg["save_path"]
    assert body["launch_command"] == cfg["launch_command"]


# ── save push / pull ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_push_and_pull_save(client):
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=AUTH)

    save_v1 = b"\x00\x01\x02\x03" * 256
    r = await client.post("/games/pokemon-emerald/save", content=save_v1, headers=AUTH)
    assert r.status_code == 200
    pushed_hash = r.json()["hash"]
    assert pushed_hash == hashlib.sha256(save_v1).hexdigest()

    r = await client.get("/games/pokemon-emerald/save", headers=AUTH)
    assert r.status_code == 200
    assert r.content == save_v1
    assert r.headers["x-save-hash"] == pushed_hash


@pytest.mark.asyncio
async def test_push_save_updates_version(client):
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=AUTH)

    save_v1 = b"save version 1"
    save_v2 = b"save version 2 with more progress"

    await client.post("/games/pokemon-emerald/save", content=save_v1, headers=AUTH)
    await client.post("/games/pokemon-emerald/save", content=save_v2, headers=AUTH)

    r = await client.get("/games/pokemon-emerald/save", headers=AUTH)
    assert r.content == save_v2
    assert r.headers["x-save-hash"] == hashlib.sha256(save_v2).hexdigest()


@pytest.mark.asyncio
async def test_pull_save_no_save_returns_204(client):
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=AUTH)
    r = await client.get("/games/pokemon-emerald/save", headers=AUTH)
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_save_meta(client):
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=AUTH)

    save_data = b"some save data"
    await client.post("/games/pokemon-emerald/save", content=save_data, headers=AUTH)

    r = await client.get("/games/pokemon-emerald/save/meta", headers=AUTH)
    assert r.status_code == 200
    meta = r.json()
    assert meta["hash"] == hashlib.sha256(save_data).hexdigest()
    assert "pushed_at" in meta


# ── locks ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_acquire_and_release_lock(client):
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=AUTH)

    r = await client.get("/games/pokemon-emerald/lock", headers=AUTH)
    assert r.json()["locked"] is False

    r = await client.post("/games/pokemon-emerald/lock", headers=AUTH)
    assert r.status_code == 200

    r = await client.get("/games/pokemon-emerald/lock", headers=AUTH)
    assert r.json()["locked"] is True

    r = await client.delete("/games/pokemon-emerald/lock", headers=AUTH)
    assert r.status_code == 200

    r = await client.get("/games/pokemon-emerald/lock", headers=AUTH)
    assert r.json()["locked"] is False


@pytest.mark.asyncio
async def test_second_device_cannot_acquire_held_lock(client):
    """Two different devices — second one must be rejected while first holds the lock."""
    auth1 = _device_auth("device-1", "PC")
    auth2 = _device_auth("device-2", "Steam Deck")

    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=auth1)

    # Device 1 acquires lock
    r = await client.post("/games/pokemon-emerald/lock", headers=auth1)
    assert r.status_code == 200

    # Device 2 should be rejected
    r = await client.post("/games/pokemon-emerald/lock", headers=auth2)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_same_device_can_reacquire_own_lock(client):
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=AUTH)

    await client.post("/games/pokemon-emerald/lock", headers=AUTH)
    r = await client.post("/games/pokemon-emerald/lock", headers=AUTH)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_get_lock_reflects_owning_device(client):
    """get_lock returns the device_id so emusync run can detect its own duplicate launch."""
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=AUTH)

    await client.post("/games/pokemon-emerald/lock", headers=AUTH)
    r = await client.get("/games/pokemon-emerald/lock", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["locked"] is True
    assert data["device_id"] == DEVICE_ID


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


# ── store direct tests ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cascade_delete_removes_saves_and_locks(client):
    """Deleting a game must remove its saves and locks from the DB."""
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=AUTH)
    await client.post("/games/pokemon-emerald/save", content=b"save data", headers=AUTH)
    await client.post("/games/pokemon-emerald/lock", headers=AUTH)

    await client.delete("/games/pokemon-emerald", headers=AUTH)

    # Game is gone
    r = await client.get("/games/pokemon-emerald", headers=AUTH)
    assert r.status_code == 404

    # Re-add the game — save and lock should not reappear
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=AUTH)
    r = await client.get("/games/pokemon-emerald/save", headers=AUTH)
    assert r.status_code == 204
    r = await client.get("/games/pokemon-emerald/lock", headers=AUTH)
    assert r.json()["locked"] is False


@pytest.mark.asyncio
async def test_stale_lock_can_be_taken_after_ttl(client):
    """A lock older than LOCK_TTL_HOURS should be claimable by another device."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        api_module.init(store, MASTER_PIN)

        # Register two devices directly via ensure_device
        store.ensure_device("device-1", "PC")
        store.ensure_device("device-2", "Deck")
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
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=AUTH)

    await client.post("/games/pokemon-emerald/save", content=b"version one", headers=AUTH)
    await client.post("/games/pokemon-emerald/save", content=b"version two", headers=AUTH)

    r = await client.get("/games/pokemon-emerald/save", headers=AUTH)
    assert r.content == b"version two"


# ── API edge cases ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_game_clears_lock_and_save(client):
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=AUTH)
    await client.post("/games/pokemon-emerald/save", content=b"save", headers=AUTH)
    await client.post("/games/pokemon-emerald/lock", headers=AUTH)

    r = await client.delete("/games/pokemon-emerald", headers=AUTH)
    assert r.status_code == 200

    # Neither save nor lock endpoint should find anything
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=AUTH)
    assert (await client.get("/games/pokemon-emerald/save", headers=AUTH)).status_code == 204
    assert (await client.get("/games/pokemon-emerald/lock", headers=AUTH)).json()["locked"] is False


@pytest.mark.asyncio
async def test_set_device_config_nonexistent_game(client):
    """PUT /games/:slug/device on a slug that doesn't exist should 404 or fail gracefully."""
    r = await client.put("/games/ghost-game/device", json={
        "rom_path": "/roms/ghost.gba",
        "save_path": "/roms/ghost.srm",
        "launch_command": "retroarch ghost.gba",
    }, headers=AUTH)
    # Should not silently succeed — foreign key constraint on game_slug
    assert r.status_code in (404, 422, 500)


@pytest.mark.asyncio
async def test_save_meta_returns_204_when_no_save(client):
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=AUTH)
    r = await client.get("/games/pokemon-emerald/save/meta", headers=AUTH)
    assert r.status_code == 204


# ── two-device save sync ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_two_device_save_sync(client):
    """Device A pushes v1, device B pulls and verifies, B pushes v2, A pulls and gets v2."""
    auth_a = _device_auth("device-a", "Gaming PC")
    auth_b = _device_auth("device-b", "Steam Deck")

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


# ── devices endpoint ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_devices(client):
    r = await client.get("/devices", headers=AUTH)
    assert r.status_code == 200
    devices = r.json()
    assert any(d["id"] == DEVICE_ID for d in devices)
    assert any(d["name"] == DEVICE_NAME for d in devices)


@pytest.mark.asyncio
async def test_list_devices_shows_all_connected(client):
    auth1 = _device_auth("d1", "PC")
    auth2 = _device_auth("d2", "Deck")

    # Trigger auto-registration for both devices
    await client.get("/games", headers=auth1)
    await client.get("/games", headers=auth2)

    r = await client.get("/devices", headers=auth1)
    ids = [d["id"] for d in r.json()]
    assert "d1" in ids
    assert "d2" in ids


# ── game rename ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_game_name(client):
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=AUTH)

    r = await client.put("/games/pokemon-emerald", json={"name": "Pokemon Emerald v2"}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["name"] == "Pokemon Emerald v2"
    assert r.json()["slug"] == "pokemon-emerald"


@pytest.mark.asyncio
async def test_update_nonexistent_game_returns_404(client):
    r = await client.put("/games/ghost-game", json={"name": "Ghost"}, headers=AUTH)
    assert r.status_code == 404


# ── clear_devices ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_clear_devices_removes_all():
    """store.clear_devices() removes all device records."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        store.ensure_device("d1", "PC")
        store.ensure_device("d2", "Deck")
        assert len(store.list_devices()) == 2
        store.clear_devices()
        assert store.list_devices() == []


# ── activity events ───────────────────────────────────────────────────────────

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


# ── update_game regression: cascade delete bug ────────────────────────────────

@pytest.mark.asyncio
async def test_update_game_name_preserves_save_and_device_config(client):
    """Renaming a game must not cascade-delete its saves or device config."""
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=AUTH)
    await client.post("/games/pokemon-emerald/save", content=b"save-data-v1", headers=AUTH)
    await client.put("/games/pokemon-emerald/device", json={
        "rom_path": "/roms/emerald.gba",
        "save_path": "/saves/emerald.sav",
        "launch_command": "retroarch emerald.gba",
    }, headers=AUTH)

    # Rename the game
    r = await client.put("/games/pokemon-emerald", json={"name": "Pokemon Emerald GBA"}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["name"] == "Pokemon Emerald GBA"

    # Save must still be present
    save_meta = await client.get("/games/pokemon-emerald/save/meta", headers=AUTH)
    assert save_meta.status_code == 200, "save was cascade-deleted by rename (regression)"

    # Device config must still be present
    device_cfg = await client.get("/games/pokemon-emerald/device", headers=AUTH)
    assert device_cfg.status_code == 200, "device config was cascade-deleted by rename (regression)"
    assert device_cfg.json()["rom_path"] == "/roms/emerald.gba"

    # The game must still appear in the list
    games = await client.get("/games", headers=AUTH)
    assert games.status_code == 200
    assert any(g["slug"] == "pokemon-emerald" for g in games.json())


@pytest.mark.asyncio
async def test_update_game_name_does_not_wipe_other_games(client):
    """Renaming one game must not affect other games' data."""
    await client.post("/games", json={"name": "Game One"}, headers=AUTH)
    await client.post("/games", json={"name": "Game Two"}, headers=AUTH)
    await client.post("/games/game-two/save", content=b"save-two", headers=AUTH)

    # Rename Game One
    await client.put("/games/game-one", json={"name": "Game One Renamed"}, headers=AUTH)

    # Game Two's save must be intact
    meta = await client.get("/games/game-two/save/meta", headers=AUTH)
    assert meta.status_code == 200, "other game's save was wiped when a different game was renamed"

    # Both games should appear in the list
    games = await client.get("/games", headers=AUTH)
    slugs = {g["slug"] for g in games.json()}
    assert "game-one" in slugs
    assert "game-two" in slugs


# ── game devices list ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_game_devices_returns_devices_with_game(client):
    """GET /games/{slug}/devices returns all devices that have the game installed."""
    auth1 = _device_auth("d1", "PC")
    auth2 = _device_auth("d2", "Steam Deck")

    # Add game (as device 1)
    await client.post("/games", json={"name": "Metroid"}, headers=auth1)

    # Device 1 sets its game config
    await client.put("/games/metroid/device", json={
        "rom_path": "/roms/metroid.gba",
        "save_path": "/saves/metroid.sav",
        "launch_command": "retroarch metroid.gba",
    }, headers=auth1)

    # Device 2 also sets its game config
    await client.put("/games/metroid/device", json={
        "rom_path": "/home/deck/roms/metroid.gba",
        "save_path": "/home/deck/saves/metroid.sav",
        "launch_command": "retroarch metroid.gba",
    }, headers=auth2)

    r = await client.get("/games/metroid/devices", headers=auth1)
    assert r.status_code == 200
    devices = r.json()
    ids = [d["id"] for d in devices]
    assert "d1" in ids
    assert "d2" in ids
    names = [d["name"] for d in devices]
    assert "PC" in names
    assert "Steam Deck" in names


@pytest.mark.asyncio
async def test_list_game_devices_empty_when_no_devices(client):
    """GET /games/{slug}/devices returns empty list if no device has the game configured."""
    await client.post("/games", json={"name": "Ghost Trick"}, headers=AUTH)

    r = await client.get("/games/ghost-trick/devices", headers=AUTH)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_list_game_devices_404_for_unknown_game(client):
    """GET /games/{slug}/devices returns 404 if the game doesn't exist."""
    r = await client.get("/games/nonexistent-game/devices", headers=AUTH)
    assert r.status_code == 404


# ── device last_ip / last_seen_at ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_devices_list_includes_last_ip_and_last_seen(client):
    """GET /devices returns last_ip and last_seen_at fields."""
    # Make any authenticated request so touch_device fires
    await client.get("/whoami", headers=AUTH)

    r = await client.get("/devices", headers=AUTH)
    assert r.status_code == 200
    device = next(d for d in r.json() if d["id"] == DEVICE_ID)
    assert "last_ip" in device
    assert "last_seen_at" in device
    assert device["last_seen_at"] is not None


@pytest.mark.asyncio
async def test_touch_device_updates_last_seen(client):
    """Each authenticated request updates last_seen_at."""
    await client.get("/whoami", headers=AUTH)
    r1 = await client.get("/devices", headers=AUTH)
    seen1 = next(d for d in r1.json() if d["id"] == DEVICE_ID)["last_seen_at"]

    import asyncio
    await asyncio.sleep(0.05)  # ensure clock advances

    await client.get("/whoami", headers=AUTH)
    r2 = await client.get("/devices", headers=AUTH)
    seen2 = next(d for d in r2.json() if d["id"] == DEVICE_ID)["last_seen_at"]

    assert seen2 >= seen1
