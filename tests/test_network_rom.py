"""Backend tests for the network-drive ROM source (issue #255).

Covers the API round-trip of the new game_device fields, the overview payload,
the device-consoles network/local folders, and a real v9→v10 schema migration.
"""
import sqlite3

import pytest

from tests.conftest import AUTH


async def _add_game(client, name="Pokemon Emerald", console="GBA"):
    r = await client.post("/games", json={"name": name, "console": console}, headers=AUTH)
    assert r.status_code == 200
    return r.json()["slug"]


@pytest.mark.asyncio
async def test_game_device_network_fields_roundtrip(client):
    slug = await _add_game(client)
    body = {
        "rom_path": "/mnt/nas/roms/GBA/Pokemon Emerald.gba",
        "save_path": "/home/me/.config/retroarch/saves/GBA/Pokemon Emerald.srm",
        "launch_command": "retroarch -L core.so '/mnt/nas/roms/GBA/Pokemon Emerald.gba'",
        "rom_folder_path": "/mnt/nas/roms/GBA",
        "rom_source": "network",
        "rom_rel_path": "GBA/Pokemon Emerald.gba",
        "local_rom_path": "",
        "rom_sha256": "",
    }
    r = await client.put(f"/games/{slug}/device", json=body, headers=AUTH)
    assert r.status_code == 200

    got = (await client.get(f"/games/{slug}/device", headers=AUTH)).json()
    assert got["rom_source"] == "network"
    assert got["rom_rel_path"] == "GBA/Pokemon Emerald.gba"
    assert got["local_rom_path"] == ""


@pytest.mark.asyncio
async def test_overview_reports_rom_source(client):
    slug = await _add_game(client)
    await client.put(f"/games/{slug}/device", json={
        "rom_path": "/mnt/nas/roms/GBA/g.gba", "save_path": "/saves/g.srm",
        "rom_source": "network", "rom_rel_path": "GBA/g.gba",
        "local_rom_path": "/local/GBA/g.gba",
    }, headers=AUTH)

    overview = (await client.get("/games/overview", headers=AUTH)).json()
    row = next(o for o in overview if o["slug"] == slug)
    assert row["rom_source"] == "network"
    assert row["rom_rel_path"] == "GBA/g.gba"
    assert row["local_rom_path"] == "/local/GBA/g.gba"


@pytest.mark.asyncio
async def test_defaults_to_local_source(client):
    """A game configured the old way (no source field) reads back as 'local'."""
    slug = await _add_game(client)
    await client.put(f"/games/{slug}/device", json={
        "rom_path": "/games/g.gba", "save_path": "/saves/g.srm",
    }, headers=AUTH)
    got = (await client.get(f"/games/{slug}/device", headers=AUTH)).json()
    assert got["rom_source"] == "local"


@pytest.mark.asyncio
async def test_device_consoles_expose_network_local_folders(client):
    slug = await _add_game(client)
    # Configuring a game auto-upserts a console row for its console.
    await client.put(f"/games/{slug}/device", json={
        "rom_path": "/mnt/nas/roms/GBA/g.gba",
        "save_path": "/saves/GBA/g.srm",
        "rom_folder_path": "/mnt/nas/roms/GBA",
        "rom_source": "network",
    }, headers=AUTH)
    whoami = (await client.get("/whoami", headers=AUTH)).json()
    consoles = (await client.get(f"/devices/{whoami['device_id']}/consoles", headers=AUTH)).json()
    assert consoles, "expected a console row to be created"
    assert "device_network_folder" in consoles[0]
    assert "device_local_folder" in consoles[0]


@pytest.mark.asyncio
async def test_network_import_populates_and_preserves_console_folders(client):
    """A network import stores the console's network/local folders; a later plain
    save/state update must not blank them (regression: localize lost its dest)."""
    slug = await _add_game(client)
    await client.put(f"/games/{slug}/device", json={
        "rom_path": "/mnt/nas/roms/GBA/g.gba",
        "save_path": "/saves/GBA/g.srm",
        "rom_folder_path": "/mnt/nas/roms/GBA",
        "rom_source": "network",
        "rom_rel_path": "GBA/g.gba",
        "device_network_folder": "/mnt/nas/roms/GBA",
        "device_local_folder": "/home/deck/Games/GBA",
    }, headers=AUTH)

    whoami = (await client.get("/whoami", headers=AUTH)).json()
    consoles = (await client.get(f"/devices/{whoami['device_id']}/consoles", headers=AUTH)).json()
    row = next(c for c in consoles if c["console_name"] == "GBA")
    assert row["device_network_folder"] == "/mnt/nas/roms/GBA"
    assert row["device_local_folder"] == "/home/deck/Games/GBA"

    # A subsequent update with no folder hints must keep them.
    await client.put(f"/games/{slug}/device", json={
        "rom_path": "/mnt/nas/roms/GBA/g.gba",
        "save_path": "/saves/GBA/g-real.srm",
        "rom_folder_path": "/mnt/nas/roms/GBA",
        "rom_source": "network",
        "rom_rel_path": "GBA/g.gba",
    }, headers=AUTH)
    consoles = (await client.get(f"/devices/{whoami['device_id']}/consoles", headers=AUTH)).json()
    row = next(c for c in consoles if c["console_name"] == "GBA")
    assert row["device_local_folder"] == "/home/deck/Games/GBA"


def test_v9_to_v10_migration(tmp_path):
    """A real v9 DB upgrades to v10, gaining the new columns without data loss."""
    from server.store import schema

    db = tmp_path / "old.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    # Minimal v9-shaped tables (pre-#255 columns only).
    conn.execute("CREATE TABLE devices (id TEXT PRIMARY KEY, name TEXT NOT NULL, last_ip TEXT, last_seen_at TEXT)")
    conn.execute("CREATE TABLE games (slug TEXT PRIMARY KEY, name TEXT NOT NULL, console TEXT DEFAULT '')")
    conn.execute("""CREATE TABLE consoles (
        id TEXT PRIMARY KEY, device_id TEXT NOT NULL, console_name TEXT NOT NULL,
        shortform_name TEXT NOT NULL, device_game_folder TEXT NOT NULL DEFAULT '',
        device_save_folder TEXT NOT NULL DEFAULT '', device_state_folder TEXT NOT NULL DEFAULT '',
        device_emulator TEXT NOT NULL DEFAULT '')""")
    conn.execute("""CREATE TABLE game_devices (
        game_slug TEXT NOT NULL, device_id TEXT NOT NULL, rom_path TEXT NOT NULL DEFAULT '',
        save_path TEXT NOT NULL DEFAULT '', launch_command TEXT NOT NULL DEFAULT '',
        state_path TEXT NOT NULL DEFAULT '', rom_folder_path TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (game_slug, device_id))""")
    conn.execute("INSERT INTO devices (id, name) VALUES ('d1', 'pc')")
    conn.execute("INSERT INTO games (slug, name, console) VALUES ('g', 'Game', 'GBA')")
    conn.execute("INSERT INTO game_devices (game_slug, device_id, rom_path) VALUES ('g', 'd1', '/r/g.gba')")
    conn.execute("PRAGMA user_version = 9")
    conn.commit()

    schema._migrate(conn, from_version=9)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == schema._SCHEMA_VERSION
    gd = conn.execute("SELECT * FROM game_devices WHERE game_slug='g'").fetchone()
    assert gd["rom_source"] == "local"          # existing rows default to local
    assert gd["rom_path"] == "/r/g.gba"         # original data preserved
    assert gd["rom_rel_path"] == ""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(consoles)").fetchall()}
    assert {"device_network_folder", "device_local_folder"} <= cols
    conn.close()
