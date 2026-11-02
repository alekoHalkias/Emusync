"""ROM identity matching (issue #731): game_devices.rom_size, duplicate prevention
in POST /games, the filename + size file search, and CLI run's moved-ROM fallback.
Real SQLite, real files, no mocks."""
import os
import sqlite3
from types import SimpleNamespace

import pytest

from cli.netrom import find_rom_by_name_size
from cli.run import _relocated_gd
from server.sync_client import GameDeviceConfig, SyncClient
from tests.conftest import AUTH, _device_auth

B = _device_auth("dev-b", "steam-deck")
ROM = "/home/a/roms/gba/Pokemon Emerald (USA).gba"


async def _import(client, headers, name, console="GBA", rom_path=ROM, size=4096, **extra):
    """POST /games with the ROM identity, then PUT this device's config."""
    r = await client.post("/games", json={
        "name": name, "console": console,
        "rom_filename": rom_path.replace("\\", "/").rsplit("/", 1)[-1], "rom_size": size,
    }, headers=headers)
    assert r.status_code == 200
    game = r.json()
    body = {"rom_path": rom_path, "save_path": "", "rom_size": size, **extra}
    assert (await client.put(f"/games/{game['slug']}/device", json=body, headers=headers)).status_code == 200
    return game


def test_v33_migration_adds_rom_size(tmp_path):
    from server.store import schema

    conn = sqlite3.connect(str(tmp_path / "old.db"))
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE game_devices (
        game_slug TEXT NOT NULL, device_id TEXT NOT NULL, rom_path TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (game_slug, device_id))""")
    conn.execute("INSERT INTO game_devices VALUES ('g', 'd1', '/roms/g.gba')")
    conn.execute("PRAGMA user_version = 33")
    conn.commit()
    schema._migrate(conn, from_version=33)
    row = conn.execute("SELECT * FROM game_devices").fetchone()
    assert row["rom_path"] == "/roms/g.gba"
    assert row["rom_size"] == 0
    assert conn.execute("PRAGMA user_version").fetchone()[0] == schema._SCHEMA_VERSION


@pytest.mark.asyncio
async def test_rom_size_roundtrip_and_preserve(client):
    g = await _import(client, AUTH, "Emerald", size=1234)
    url = f"/games/{g['slug']}/device"
    assert (await client.get(url, headers=AUTH)).json()["rom_size"] == 1234
    overview = {o["slug"]: o for o in (await client.get("/games/overview", headers=AUTH)).json()}
    assert overview[g["slug"]]["rom_size"] == 1234
    # A client that predates the field PUTs the whole row without it: size kept.
    await client.put(url, json={"rom_path": ROM, "save_path": "/s.srm"}, headers=AUTH)
    assert (await client.get(url, headers=AUTH)).json()["rom_size"] == 1234
    await client.put(url, json={"rom_path": ROM, "save_path": "", "rom_size": 0}, headers=AUTH)
    assert (await client.get(url, headers=AUTH)).json()["rom_size"] == 0


@pytest.mark.asyncio
async def test_add_game_matches_existing_rom(client):
    first = await _import(client, AUTH, "Pokemon Emerald")
    assert first["matched"] is False
    second = await _import(client, B, "Emerald", rom_path="/home/deck/roms/Pokemon Emerald (USA).gba")
    assert second["matched"] is True
    assert second["slug"] == first["slug"]
    assert second["name"] == "Pokemon Emerald"
    assert len((await client.get("/games", headers=AUTH)).json()) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("over", [
    {"rom_size": 4097},                              # same name, other size
    {"console": "SNES"},                             # other console
    {"rom_size": 0},                                 # size unknown
    {"rom_filename": "", "rom_size": 0},             # old client, no ROM fields
])
async def test_add_game_no_match(client, over):
    first = await _import(client, AUTH, "Pokemon Emerald")
    body = {"name": "Emerald", "console": "GBA", "rom_filename": "Pokemon Emerald (USA).gba", "rom_size": 4096}
    body.update(over)
    r = (await client.post("/games", json=body, headers=B)).json()
    assert r["matched"] is False
    assert r["slug"] != first["slug"]


@pytest.mark.asyncio
async def test_add_game_match_casefold_and_backslash(client):
    first = await _import(client, AUTH, "Pokemon Emerald", rom_path=r"C:\Roms\GBA\POKEMON EMERALD (USA).GBA")
    r = (await client.post("/games", json={
        "name": "Emerald", "console": "GBA", "rom_filename": "pokemon emerald (usa).gba", "rom_size": 4096,
    }, headers=B)).json()
    assert r["matched"] is True and r["slug"] == first["slug"]


@pytest.mark.asyncio
async def test_add_game_match_via_rel_path(client):
    first = await _import(client, AUTH, "Pokemon Emerald", rom_path="/mnt/nas/x.gba",
                          rom_source="network", rom_rel_path="GBA/Pokemon Emerald (USA).gba")
    r = (await client.post("/games", json={
        "name": "Emerald", "console": "GBA", "rom_filename": "Pokemon Emerald (USA).gba", "rom_size": 4096,
    }, headers=B)).json()
    assert r["matched"] is True and r["slug"] == first["slug"]


@pytest.mark.asyncio
async def test_add_game_oldest_duplicate_wins(client):
    first = await _import(client, AUTH, "Pokemon Emerald")
    # A pre-#731 duplicate: created without ROM fields, then given the same ROM.
    dup = (await client.post("/games", json={"name": "Emerald Dup", "console": "GBA"}, headers=B)).json()
    await client.put(f"/games/{dup['slug']}/device", json={"rom_path": ROM, "save_path": "", "rom_size": 4096}, headers=B)
    r = (await client.post("/games", json={
        "name": "Third", "console": "GBA", "rom_filename": "Pokemon Emerald (USA).gba", "rom_size": 4096,
    }, headers=_device_auth("dev-c", "laptop"))).json()
    assert r["slug"] == first["slug"]


def _rom(path, size):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"\0" * size)
    return path


def test_find_rom_unique_hit(tmp_path):
    p = _rom(str(tmp_path / "a" / "Game.gba"), 10)
    assert find_rom_by_name_size([str(tmp_path)], "game.GBA", 10) == p
    assert find_rom_by_name_size([str(tmp_path)], "/old/place/Game.gba", 10) == p


@pytest.mark.parametrize("name,size", [("Game.gba", 11), ("Game.gba", 0), ("Other.gba", 10)])
def test_find_rom_no_match(tmp_path, name, size):
    _rom(str(tmp_path / "Game.gba"), 10)
    assert find_rom_by_name_size([str(tmp_path)], name, size) is None


def test_find_rom_ambiguous_is_none(tmp_path):
    _rom(str(tmp_path / "a" / "Game.gba"), 10)
    _rom(str(tmp_path / "b" / "Game.gba"), 10)
    assert find_rom_by_name_size([str(tmp_path)], "Game.gba", 10) is None


def test_find_rom_same_file_via_two_roots_counts_once(tmp_path):
    p = _rom(str(tmp_path / "a" / "Game.gba"), 10)
    assert find_rom_by_name_size([str(tmp_path), str(tmp_path / "a"), str(tmp_path / "missing")],
                                 "Game.gba", 10) in {p, os.path.realpath(p)}


def _gd(**kw):
    base = dict(rom_source="local", rom_path="/gone/Game.gba", local_rom_path="",
                rom_size=10, launch_command="emu '/gone/Game.gba'")
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.mark.parametrize("cmd,expect", [
    ("emu '/gone/Game.gba'", "emu '{p}'"),
    ('emu "%ROM%"', 'emu "%ROM%"'),
])
def test_relocated_gd_hit_rewrites_copy_only(tmp_path, cmd, expect):
    p = _rom(str(tmp_path / "local" / "Game.gba"), 10)
    gd = _gd(launch_command=cmd)
    consoles = [{"console_name": "GBA", "device_local_folder": str(tmp_path / "local")},
                {"console_name": "SNES", "device_local_folder": "/elsewhere"}]
    moved = _relocated_gd(gd, consoles, "gba")
    assert moved.rom_path == p and moved.rom_source == "local"
    assert moved.launch_command == expect.format(p=p)
    assert gd.rom_path == "/gone/Game.gba" and gd.launch_command == cmd


@pytest.mark.parametrize("files,over", [
    ([], {}),                                         # nothing found
    (["a/Game.gba", "b/Game.gba"], {}),               # ambiguous
    (["a/Game.gba"], {"rom_size": 0}),                # size unknown
    (["a/Game.gba"], {"rom_path": "PRESENT"}),        # ROM not missing
])
def test_relocated_gd_none(tmp_path, files, over):
    for f in files:
        _rom(str(tmp_path / f), 10)
    if over.get("rom_path") == "PRESENT":
        over = {"rom_path": _rom(str(tmp_path / "here" / "Game.gba"), 10)}
    consoles = [{"console_name": "GBA", "device_game_folder": str(tmp_path), "device_extra_folders": []}]
    assert _relocated_gd(_gd(**over), consoles, "GBA") is None


def test_sync_client_add_game_reports_match(live_server):
    a = SyncClient(live_server["host"], live_server["port"], "", "dev-a", "pc")
    b = SyncClient(live_server["host"], live_server["port"], "", "dev-b", "deck")
    first = a.add_game("Pokemon Emerald", "GBA", rom_filename="Emerald.gba", rom_size=99)
    a.set_game_device(first["slug"], GameDeviceConfig(rom_path="/r/Emerald.gba", rom_size=99))
    second = b.add_game("Emerald", "GBA", rom_filename="emerald.gba", rom_size=99)
    assert second["matched"] is True and second["slug"] == first["slug"]
    assert b.get_game_device(second["slug"]) is None
