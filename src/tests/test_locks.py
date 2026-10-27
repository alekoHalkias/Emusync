"""Lock acquire/release, contention, and stale-lock TTL tests."""
from __future__ import annotations

import tempfile
from datetime import datetime, timezone, timedelta

import pytest

from server import api as api_module
from server.store import Store, LOCK_TTL_HOURS
from tests.conftest import AUTH, DEVICE_ID, MASTER_PIN, _device_auth


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
async def test_heartbeat_reacquire_refreshes_acquired_at(client):
    """The lock heartbeat re-acquires as the same holder, bumping acquired_at so a
    long session never crosses the TTL and gets stolen (issue #238)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        api_module.init(store, MASTER_PIN)

        store.ensure_device("device-1", "PC")
        store.ensure_device("device-2", "Deck")
        store.add_game("test-game", "Test Game")

        # Device 1 holds a lock that is almost stale.
        store.acquire_lock("test-game", "device-1")
        near_stale = (datetime.now(timezone.utc) - timedelta(hours=LOCK_TTL_HOURS - 0.1)).isoformat()
        store._conn.execute(
            "UPDATE locks SET acquired_at = ? WHERE game_slug = ?",
            (near_stale, "test-game"),
        )
        store._conn.commit()

        # A heartbeat beat (same-holder re-acquire) refreshes the timestamp.
        store.acquire_lock("test-game", "device-1")

        # Now another device must still be blocked — the lock is fresh again.
        with pytest.raises(ValueError):
            store.acquire_lock("test-game", "device-2")
        assert store.get_lock("test-game").device_id == "device-1"


@pytest.mark.asyncio
async def test_release_device_locks_frees_all_held_locks(client):
    """When a device goes offline its locks are released so a crashed device
    doesn't block games until the TTL (issue #238)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        api_module.init(store, MASTER_PIN)

        store.ensure_device("device-1", "PC")
        store.ensure_device("device-2", "Deck")
        store.add_game("game-a", "Game A")
        store.add_game("game-b", "Game B")
        store.add_game("game-c", "Game C")

        store.acquire_lock("game-a", "device-1")
        store.acquire_lock("game-b", "device-1")
        store.acquire_lock("game-c", "device-2")

        freed = store.release_device_locks("device-1")
        assert sorted(freed) == ["game-a", "game-b"]

        # device-1's locks are gone; device-2's is untouched.
        assert store.get_lock("game-a") is None
        assert store.get_lock("game-b") is None
        assert store.get_lock("game-c").device_id == "device-2"

        # A second call is a no-op (returns nothing to free).
        assert store.release_device_locks("device-1") == []
