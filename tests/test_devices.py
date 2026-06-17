"""Device listing, presence, compare, game-device coverage, and deletion tests."""
from __future__ import annotations

import asyncio
import tempfile

import pytest

from server.store import Store, GameDevice
from tests.conftest import AUTH, DEVICE_ID, DEVICE_NAME, _device_auth


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


# ── clear_devices ─────────────────────────────────────────────────────────────

def test_clear_devices_removes_all():
    """store.clear_devices() removes all device records."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        store.ensure_device("d1", "PC")
        store.ensure_device("d2", "Deck")
        assert len(store.list_devices()) == 2
        store.clear_devices()
        assert store.list_devices() == []


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

    await asyncio.sleep(0.05)  # ensure clock advances

    await client.get("/whoami", headers=AUTH)
    r2 = await client.get("/devices", headers=AUTH)
    seen2 = next(d for d in r2.json() if d["id"] == DEVICE_ID)["last_seen_at"]

    assert seen2 >= seen1


# ── device compare (API layer) ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_device_compare_shared_and_missing(client):
    """
    Three games, two devices.
    Device A has games 1 & 2; device B has games 2 & 3.
    From device A's perspective: game 1 is exclusive, game 2 is shared, game 3 is missing.
    """
    auth_a = _device_auth("dev-a", "PC")
    auth_b = _device_auth("dev-b", "Steam Deck")

    await client.post("/games", json={"name": "Game One"},   headers=auth_a)
    await client.post("/games", json={"name": "Game Two"},   headers=auth_a)
    await client.post("/games", json={"name": "Game Three"}, headers=auth_b)

    # Device A configures games 1 & 2
    for slug in ("game-one", "game-two"):
        await client.put(f"/games/{slug}/device",
                         json={"save_path": f"/saves/{slug}.sav"}, headers=auth_a)

    # Device B configures games 2 & 3
    for slug in ("game-two", "game-three"):
        await client.put(f"/games/{slug}/device",
                         json={"save_path": f"/saves/{slug}.sav"}, headers=auth_b)

    # From device A: which games are on it?
    r = await client.get("/games/game-one/devices",   headers=auth_a)
    assert {d["id"] for d in r.json()} == {"dev-a"}

    r = await client.get("/games/game-two/devices",   headers=auth_a)
    assert {d["id"] for d in r.json()} == {"dev-a", "dev-b"}

    r = await client.get("/games/game-three/devices", headers=auth_a)
    assert {d["id"] for d in r.json()} == {"dev-b"}   # dev-a is missing this one


@pytest.mark.asyncio
async def test_device_compare_all_match(client):
    """Both devices have all games — no missing entries."""
    auth_a = _device_auth("dev-a", "PC")
    auth_b = _device_auth("dev-b", "Steam Deck")

    await client.post("/games", json={"name": "Shared Game"}, headers=auth_a)
    for auth in (auth_a, auth_b):
        await client.put("/games/shared-game/device",
                         json={"save_path": "/saves/shared.sav"}, headers=auth)

    r_a = await client.get("/games/shared-game/devices", headers=auth_a)
    assert {d["id"] for d in r_a.json()} == {"dev-a", "dev-b"}


@pytest.mark.asyncio
async def test_device_compare_no_games(client):
    """Server has no games — compare returns an empty list."""
    r = await client.get("/games", headers=AUTH)
    assert r.json() == []


# ── game-devices for a device ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_game_devices_for_device(client):
    """GET /game-devices returns only games configured for the calling device."""
    auth_a = _device_auth("dev-a", "PC")
    auth_b = _device_auth("dev-b", "Deck")

    await client.post("/games", json={"name": "Alpha"}, headers=auth_a)
    await client.post("/games", json={"name": "Beta"},  headers=auth_a)
    await client.put("/games/alpha/device", json={"rom_path": "/roms/Alpha.gba"}, headers=auth_a)
    await client.put("/games/beta/device",  json={"rom_path": "/roms/Beta.gba"},  headers=auth_b)

    r = await client.get("/game-devices", headers=auth_a)
    assert r.status_code == 200
    slugs = {g["slug"] for g in r.json()}
    assert slugs == {"alpha"}  # dev-a only configured alpha


@pytest.mark.asyncio
async def test_devices_list_includes_is_online(client):
    """GET /devices includes is_online bool for each device."""
    r = await client.get("/devices", headers=AUTH)
    assert r.status_code == 200
    devices = r.json()
    assert len(devices) >= 1
    for d in devices:
        assert "is_online" in d
        assert isinstance(d["is_online"], bool)


@pytest.mark.asyncio
async def test_device_game_devices_endpoint(client):
    """GET /devices/{id}/game-devices returns games for that specific device."""
    auth_a = _device_auth("gd-dev-a", "PC")
    auth_b = _device_auth("gd-dev-b", "Deck")

    await client.post("/games", json={"name": "Halo"}, headers=auth_a)
    await client.post("/games", json={"name": "Doom"}, headers=auth_b)
    await client.put("/games/halo/device", json={"rom_path": "/roms/Halo.iso"}, headers=auth_a)
    await client.put("/games/doom/device", json={"rom_path": "/roms/Doom.wad"}, headers=auth_b)

    # Calling device (auth_a) fetches games on auth_b's device
    r = await client.get("/devices/gd-dev-b/game-devices", headers=auth_a)
    assert r.status_code == 200
    slugs = {g["slug"] for g in r.json()}
    assert slugs == {"doom"}
    assert "halo" not in slugs


# ── device deletion with dependents (#202) ─────────────────────────────────────

def test_remove_device_with_games_and_saves():
    """Deleting a device that has configured games / saves / locks must not raise
    a FOREIGN KEY violation (foreign_keys is ON per connection)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        store.ensure_device("dev1", "PC")
        store.add_game("metroid", "Metroid", "GBA")
        store.set_game_device(
            GameDevice(game_slug="metroid", device_id="dev1", rom_path="/x/m.gba",
                       save_path="", launch_command="", state_path="", rom_folder_path="")
        )
        store.push_save("metroid", "dev1", b"savedata")
        store.acquire_lock("metroid", "dev1")

        store.remove_device("dev1")  # must not raise

        assert all(d.id != "dev1" for d in store.list_devices())
        assert store.get_lock("metroid") is None
        assert store.get_game_device("metroid", "dev1") is None


@pytest.mark.asyncio
async def test_delete_device_endpoint_with_configured_game(make_client, tmp_path):
    """DELETE /devices/{id} succeeds for a device that has a game configured."""
    c = await make_client(data_dir=str(tmp_path))
    auth = _device_auth("dev-x", "PC")
    await c.post("/games", json={"name": "Zelda", "console": "GBA"}, headers=auth)
    await c.put(
        "/games/zelda/device",
        json={"rom_path": "/roms/zelda.gba", "save_path": "/saves/zelda.srm"},
        headers=auth,
    )
    r = await c.delete("/devices/dev-x", headers=auth)
    assert r.status_code == 200
