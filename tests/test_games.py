"""Game CRUD, per-device game config, rename, and cascade-delete tests."""
from __future__ import annotations

import pytest

from tests.conftest import AUTH, _device_auth


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


@pytest.mark.asyncio
async def test_update_game_sgdb_id(client):
    """A picked SteamGridDB match (issue #325) persists and round-trips."""
    await client.post("/games", json={"name": "Test Game"}, headers=AUTH)

    r = await client.get("/games/test-game", headers=AUTH)
    assert r.json()["sgdb_game_id"] is None

    r = await client.put("/games/test-game", json={"name": "Test Game", "sgdb_game_id": 12345}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["sgdb_game_id"] == 12345

    r = await client.get("/games/test-game", headers=AUTH)
    assert r.json()["sgdb_game_id"] == 12345


@pytest.mark.asyncio
async def test_update_game_without_sgdb_id_leaves_existing_value(client):
    """A plain rename (no sgdb_game_id in the request) must not clear a
    previously-picked match — mirrors how a plain rename doesn't clear console."""
    await client.post("/games", json={"name": "Test Game"}, headers=AUTH)
    await client.put("/games/test-game", json={"name": "Test Game", "sgdb_game_id": 12345}, headers=AUTH)

    r = await client.put("/games/test-game", json={"name": "Renamed"}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["sgdb_game_id"] == 12345


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


# ── per-device unlink (issue #343) ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_remove_game_device_unlinks_only_calling_device(client):
    """DELETE /games/:slug/device removes only the calling device's config —
    the game, its other devices, and its saves must be untouched."""
    auth1 = _device_auth("d1", "PC")
    auth2 = _device_auth("d2", "Steam Deck")
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=auth1)
    await client.put("/games/pokemon-emerald/device", json={
        "rom_path": "/pc/emerald.gba", "save_path": "/pc/emerald.srm", "launch_command": "retroarch",
    }, headers=auth1)
    await client.put("/games/pokemon-emerald/device", json={
        "rom_path": "/deck/emerald.gba", "save_path": "/deck/emerald.srm", "launch_command": "retroarch",
    }, headers=auth2)
    await client.post("/games/pokemon-emerald/save", content=b"save-data", headers=auth1)

    r = await client.delete("/games/pokemon-emerald/device", headers=auth1)
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # d1's config is gone
    r = await client.get("/games/pokemon-emerald/device", headers=auth1)
    assert r.status_code == 404

    # d2's config, the game, and the save are untouched
    r = await client.get("/games/pokemon-emerald/device", headers=auth2)
    assert r.status_code == 200
    assert r.json()["rom_path"] == "/deck/emerald.gba"

    r = await client.get("/games/pokemon-emerald", headers=auth1)
    assert r.status_code == 200

    save_meta = await client.get("/games/pokemon-emerald/save/meta", headers=auth1)
    assert save_meta.status_code == 200


@pytest.mark.asyncio
async def test_remove_game_device_idempotent_when_no_config(client):
    """Calling it twice (or with no device config to begin with) is a no-op ok,
    not an error — mirrors DELETE semantics elsewhere in the API."""
    await client.post("/games", json={"name": "Test Game"}, headers=AUTH)

    r = await client.delete("/games/test-game/device", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["ok"] is True

    r = await client.delete("/games/test-game/device", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["ok"] is True


@pytest.mark.asyncio
async def test_remove_game_device_nonexistent_game_returns_404(client):
    r = await client.delete("/games/does-not-exist/device", headers=AUTH)
    assert r.status_code == 404


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


# ── cascade delete ────────────────────────────────────────────────────────────

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
