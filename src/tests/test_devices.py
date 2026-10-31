"""Device listing, presence, compare, game-device coverage, and deletion tests."""
from __future__ import annotations

import asyncio
import threading
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from server import api as api_module
from server.api import _core
from server.store import Store, GameDevice
from tests.conftest import AUTH, DEVICE_ID, DEVICE_NAME, MASTER_PIN, _device_auth


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


# ── editable console folders (#539) ───────────────────────────────────────────

async def _seed_console(client) -> dict:
    await client.post("/games", json={"name": "Chrono", "console": "SNES"}, headers=AUTH)
    r = await client.put(
        "/games/chrono/device",
        json={"rom_path": "/roms/snes/chrono.sfc", "save_path": "/saves/snes/chrono.srm"},
        headers=AUTH,
    )
    assert r.status_code == 200
    consoles = (await client.get(f"/devices/{DEVICE_ID}/consoles", headers=AUTH)).json()
    assert len(consoles) == 1
    return consoles[0]


@pytest.mark.asyncio
async def test_update_device_console_edits_folders(client):
    c = await _seed_console(client)
    body = {k: v for k, v in c.items() if k not in ("id", "console_name")}
    body["device_save_folder"] = "/new/saves"
    body["device_emulator"] = "retroarch"
    r = await client.put(f"/devices/{DEVICE_ID}/consoles/{c['id']}", json=body, headers=AUTH)
    assert r.status_code == 200
    got = (await client.get(f"/devices/{DEVICE_ID}/consoles", headers=AUTH)).json()[0]
    assert got["device_save_folder"] == "/new/saves"
    assert got["device_emulator"] == "retroarch"


@pytest.mark.asyncio
async def test_update_device_console_errors(client):
    c = await _seed_console(client)
    r = await client.put(f"/devices/{DEVICE_ID}/consoles/nope", json={}, headers=AUTH)
    assert r.status_code == 404
    other = _device_auth("d2", "Deck")
    r = await client.put(f"/devices/{DEVICE_ID}/consoles/{c['id']}", json={}, headers=other)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_game_config_save_does_not_overwrite_edited_console_folders(client):
    """Regression: set_game_device used to rewrite save/state/emulator on every call."""
    c = await _seed_console(client)
    body = {k: v for k, v in c.items() if k not in ("id", "console_name")}
    body["device_save_folder"] = "/new/saves"
    body["device_state_folder"] = "/new/states"
    body["device_emulator"] = "custom"
    await client.put(f"/devices/{DEVICE_ID}/consoles/{c['id']}", json=body, headers=AUTH)
    await client.put(
        "/games/chrono/device",
        json={"rom_path": "/roms/snes/chrono.sfc", "save_path": "/saves/snes/chrono.srm"},
        headers=AUTH,
    )
    got = (await client.get(f"/devices/{DEVICE_ID}/consoles", headers=AUTH)).json()[0]
    assert got["device_save_folder"] == "/new/saves"
    assert got["device_state_folder"] == "/new/states"
    assert got["device_emulator"] == "custom"


# ── console extra folders (#629) ─────────────────────────────────────────────

async def _put_game(client, name: str, rom: str, save: str = "", **extra) -> str:
    slug = name.lower()
    await client.post("/games", json={"name": name, "console": "SNES"}, headers=AUTH)
    r = await client.put(f"/games/{slug}/device",
                         json={"rom_path": rom, "save_path": save, **extra}, headers=AUTH)
    assert r.status_code == 200
    return slug


async def _consoles(client) -> list[dict]:
    return (await client.get(f"/devices/{DEVICE_ID}/consoles", headers=AUTH)).json()


async def _put_console(client, c: dict, **changes) -> None:
    body = {k: v for k, v in c.items() if k not in ("id", "console_name")}
    body.update(changes)
    r = await client.put(f"/devices/{DEVICE_ID}/consoles/{c['id']}", json=body, headers=AUTH)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_console_extra_folders_default_empty(client):
    c = await _seed_console(client)
    assert c["device_extra_folders"] == []


@pytest.mark.asyncio
async def test_put_console_extra_folders_roundtrip_and_normalize(client):
    c = await _seed_console(client)
    await _put_console(client, c, device_extra_folders=["/roms2", "  /roms3 ", "", "/roms2", c["device_game_folder"]])
    assert (await _consoles(client))[0]["device_extra_folders"] == ["/roms2", "/roms3"]


@pytest.mark.asyncio
async def test_put_console_without_extra_folders_preserves_them(client):
    """Regression: a pre-#629 client omits the field and must not blank the list."""
    c = await _seed_console(client)
    await _put_console(client, c, device_extra_folders=["/roms2"])
    body = {k: v for k, v in c.items() if k not in ("id", "console_name", "device_extra_folders")}
    r = await client.put(f"/devices/{DEVICE_ID}/consoles/{c['id']}", json=body, headers=AUTH)
    assert r.status_code == 200
    assert (await _consoles(client))[0]["device_extra_folders"] == ["/roms2"]
    await _put_console(client, c, device_extra_folders=[])
    assert (await _consoles(client))[0]["device_extra_folders"] == []


@pytest.mark.asyncio
async def test_new_game_folder_becomes_extra_not_second_row(client):
    await _seed_console(client)
    await _put_game(client, "Zelda", "/other/snes/zelda.sfc", "/saves/snes/zelda.srm")
    rows = await _consoles(client)
    assert len(rows) == 1
    assert rows[0]["device_extra_folders"] == ["/other"]
    # Same folder again and a nested folder add nothing.
    await _put_game(client, "Mario", "/other/snes/mario.sfc", "/saves/snes/mario.srm")
    await _put_game(client, "Metroid", "/roms/snes/usa/metroid.sfc")
    rows = await _consoles(client)
    assert len(rows) == 1 and rows[0]["device_extra_folders"] == ["/other"]


@pytest.mark.asyncio
async def test_save_only_game_adds_no_row_or_extra(client):
    await _seed_console(client)
    await _put_game(client, "Zelda", "", "/saves/snes/zelda.srm")
    rows = await _consoles(client)
    assert len(rows) == 1 and rows[0]["device_extra_folders"] == []


@pytest.mark.asyncio
async def test_chosen_emulator_survives_new_folder_game(client):
    """AC: the derived emulator never overwrites a user-chosen one, including via the extras path."""
    c = await _seed_console(client)
    await _put_console(client, c, device_emulator="custom")
    await _put_game(client, "Zelda", "/other/snes/zelda.sfc", "/elsewhere/Snes9x/zelda.srm")
    assert (await _consoles(client))[0]["device_emulator"] == "custom"


@pytest.mark.asyncio
async def test_legacy_two_row_console_keeps_both_rows(client):
    await _seed_console(client)
    store = _core._get_store()
    first = store.list_consoles(DEVICE_ID)[0]
    from server.store.models import Console
    store.set_console(Console(id="legacy-2", device_id=DEVICE_ID, console_name="SNES",
                              shortform_name="snes", device_game_folder="/legacy"))
    await _put_game(client, "Zelda", "/legacy/snes/zelda.sfc")
    await _put_game(client, "Mario", "/roms/snes/mario.sfc")
    rows = await _consoles(client)
    assert {r["device_game_folder"] for r in rows} == {first.device_game_folder, "/legacy"}
    assert all(r["device_extra_folders"] == [] for r in rows)


@pytest.mark.asyncio
async def test_network_game_folder_is_not_added_as_extra(client):
    c = await _seed_console(client)
    await _put_console(client, c, device_network_folder="/mnt/nas/snes")
    await _put_game(client, "Zelda", "/mnt/nas/snes/zelda.sfc", "/saves/snes/zelda.srm",
                    rom_folder_path="/mnt/nas/snes", rom_source="network")
    assert (await _consoles(client))[0]["device_extra_folders"] == []


# ── presence monitor vs live updates (#597) ───────────────────────────────────

def test_monitor_sweep_concurrent_with_presence_updates():
    """A monitor sweep racing with live presence updates must not crash or
    double-log: the stale device's lock is released exactly once and its
    game_stopped event recorded, with the updates thread seeing no errors."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        api_module.init(store, MASTER_PIN)
        store.ensure_device("stale-dev", "Old PC")
        store.add_game("g1", "Game One", "GBA")
        store.acquire_lock("g1", "stale-dev")
        # Age the device past the offline threshold (bypassing touch_device,
        # which can only stamp "now").
        old = (datetime.now(timezone.utc) - timedelta(
            seconds=_core.OFFLINE_TIMEOUT_SECONDS + 60)).isoformat()
        store._conn.execute(
            "UPDATE devices SET last_ip = ?, last_seen_at = ? WHERE id = ?",
            ("127.0.0.1", old, "stale-dev"),
        )
        store._conn.commit()
        with _core._presence_lock:
            _core._online_devices.add("stale-dev")
            _core._device_names["stale-dev"] = "Old PC"

        # Run the REAL monitor for exactly one iteration: the first patched
        # sleep returns instantly, the next raises KeyboardInterrupt, which
        # threading treats as a silent thread exit.
        countdown = iter((0,))

        def one_shot_sleep(_seconds):
            try:
                next(countdown)
            except StopIteration:
                raise KeyboardInterrupt

        def run_monitor_once():
            try:
                _core._monitor_presence()
            except KeyboardInterrupt:
                pass  # one_shot_sleep's stop signal

        with patch("time.sleep", one_shot_sleep):
            monitor = threading.Thread(target=run_monitor_once)
            monitor.start()

            # Concurrently simulate _auth-side presence updates.
            errors: list[Exception] = []

            def live_updates():
                try:
                    # Only the lock-guarded bookkeeping _auth does; raw sqlite
                    # touches from other request handlers are serialized by
                    # SQLite itself, not by _presence_lock.
                    for _ in range(200):
                        with _core._presence_lock:
                            _core._online_devices.add("stale-dev")
                            _core._device_names["stale-dev"] = "Old PC"
                except Exception as exc:
                    errors.append(exc)

            updates = threading.Thread(target=live_updates)
            updates.start()
            updates.join(10)
            monitor.join(10)

        assert errors == []
        assert not monitor.is_alive()
        assert store.get_lock("g1") is None
        events = store.list_events()
        stopped = [
            e for e in events
            if e["type"] == "game_stopped" and e["game_slug"] == "g1"
            and e["device_id"] == "stale-dev"
        ]
        assert len(stopped) == 1


# ── import_remote_path cross-device validation (#642) ─────────────────────────

@pytest.mark.asyncio
async def test_put_console_import_remote_path_mismatch(client):
    """Another device with a different import_remote_path must be rejected."""
    from tests.conftest import _device_auth

    # Seed device-2 with a different remote path for SNES
    auth2 = _device_auth("device-xyz", "other-pc")
    await client.post("/games", json={"name": "ActRaiser", "console": "SNES"}, headers=auth2)
    r = await client.put(
        "/games/actraiser/device",
        json={"rom_path": "/roms/snes/actraiser.sfc", "save_path": "/saves/snes/actraiser.srm"},
        headers=auth2,
    )
    assert r.status_code == 200
    consoles2 = (await client.get(f"/devices/device-xyz/consoles", headers=auth2)).json()
    c2 = consoles2[0]
    body = {k: v for k, v in c2.items() if k not in ("id", "console_name")}
    body["import_is_network"] = True
    body["import_remote_path"] = "/mnt/nas/other"
    r = await client.put(f"/devices/device-xyz/consoles/{c2['id']}", json=body, headers=auth2)
    assert r.status_code == 200

    # Now device-1 tries to set a different remote path for SNES
    c = await _seed_console(client)
    body = {k: v for k, v in c.items() if k not in ("id", "console_name")}
    body["import_is_network"] = True
    body["import_remote_path"] = "/mnt/nas/different"
    r = await client.put(f"/devices/{DEVICE_ID}/consoles/{c['id']}", json=body, headers=AUTH)
    assert r.status_code == 400
    assert "Remote path mismatch" in r.json()["detail"]


@pytest.mark.asyncio
async def test_put_console_import_remote_path_agree(client):
    """Two devices setting the same import_remote_path must succeed."""
    from tests.conftest import _device_auth

    auth2 = _device_auth("device-xyz", "other-pc")
    await client.post("/games", json={"name": "ActRaiser", "console": "SNES"}, headers=auth2)
    r = await client.put(
        "/games/actraiser/device",
        json={"rom_path": "/roms/snes/actraiser.sfc", "save_path": "/saves/snes/actraiser.srm"},
        headers=auth2,
    )
    assert r.status_code == 200
    consoles2 = (await client.get(f"/devices/device-xyz/consoles", headers=auth2)).json()
    c2 = consoles2[0]
    body = {k: v for k, v in c2.items() if k not in ("id", "console_name")}
    body["import_is_network"] = True
    body["import_remote_path"] = "/mnt/nas/snes"
    r = await client.put(f"/devices/device-xyz/consoles/{c2['id']}", json=body, headers=auth2)
    assert r.status_code == 200

    # Device-1 sets the same remote path
    c = await _seed_console(client)
    body = {k: v for k, v in c.items() if k not in ("id", "console_name")}
    body["import_is_network"] = True
    body["import_remote_path"] = "/mnt/nas/snes"
    r = await client.put(f"/devices/{DEVICE_ID}/consoles/{c['id']}", json=body, headers=AUTH)
    assert r.status_code == 200
    got = (await client.get(f"/devices/{DEVICE_ID}/consoles", headers=AUTH)).json()[0]
    assert got["import_remote_path"] == "/mnt/nas/snes"


@pytest.mark.asyncio
async def test_put_console_empty_remote_path_skips_validation(client):
    """Setting import_remote_path='' must bypass cross-device validation."""
    from tests.conftest import _device_auth

    # Device-2 sets a remote path
    auth2 = _device_auth("device-xyz", "other-pc")
    await client.post("/games", json={"name": "ActRaiser", "console": "SNES"}, headers=auth2)
    r = await client.put(
        "/games/actraiser/device",
        json={"rom_path": "/roms/snes/actraiser.sfc", "save_path": "/saves/snes/actraiser.srm"},
        headers=auth2,
    )
    assert r.status_code == 200
    consoles2 = (await client.get(f"/devices/device-xyz/consoles", headers=auth2)).json()
    c2 = consoles2[0]
    body = {k: v for k, v in c2.items() if k not in ("id", "console_name")}
    body["import_is_network"] = True
    body["import_remote_path"] = "/mnt/nas/snes"
    r = await client.put(f"/devices/device-xyz/consoles/{c2['id']}", json=body, headers=auth2)
    assert r.status_code == 200

    # Device-1 sets import_is_network=True but empty remote_path
    c = await _seed_console(client)
    body = {k: v for k, v in c.items() if k not in ("id", "console_name")}
    body["import_is_network"] = True
    body["import_remote_path"] = ""
    r = await client.put(f"/devices/{DEVICE_ID}/consoles/{c['id']}", json=body, headers=AUTH)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_put_console_import_is_network_without_remote_path(client):
    """Setting import_is_network=True with empty import_remote_path is valid."""
    c = await _seed_console(client)
    body = {k: v for k, v in c.items() if k not in ("id", "console_name")}
    body["import_is_network"] = True
    body["import_remote_path"] = ""
    r = await client.put(f"/devices/{DEVICE_ID}/consoles/{c['id']}", json=body, headers=AUTH)
    assert r.status_code == 200
    got = (await client.get(f"/devices/{DEVICE_ID}/consoles", headers=AUTH)).json()[0]
    assert got["import_is_network"] is True
    assert got["import_remote_path"] == ""

