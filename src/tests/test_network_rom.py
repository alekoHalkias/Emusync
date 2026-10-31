"""Backend tests for the network-drive ROM source (issue #255).

Covers the API round-trip of the new game_device fields, the overview payload,
the device-consoles network/local folders, and a real v9→v10 schema migration.
"""
import sqlite3

import pytest

from tests.conftest import AUTH, _device_auth


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
async def test_network_source_discovery_across_devices(client):
    """A device that doesn't have the game can discover another device's network
    config so it can join the rel-path to its own mount root (issue #270)."""
    slug = await _add_game(client)
    # Device A configures the game on a network share.
    auth_a = _device_auth("dev-a", "Gaming PC")
    await client.put(f"/games/{slug}/device", json={
        "rom_path": "/mnt/nas/roms/GBA/Pokemon Emerald.gba",
        "save_path": "/home/a/saves/GBA/Pokemon Emerald/Pokemon Emerald.srm",
        "state_path": "/home/a/states/GBA/Pokemon Emerald",
        "launch_command": "retroarch -L core.so '/mnt/nas/roms/GBA/Pokemon Emerald.gba'",
        "rom_folder_path": "/mnt/nas/roms/GBA",
        "rom_source": "network", "rom_rel_path": "GBA/Pokemon Emerald.gba",
    }, headers=auth_a)

    # Device B (no config for this game) discovers the network source.
    auth_b = _device_auth("dev-b", "Steam Deck")
    r = await client.get(f"/games/{slug}/network-source", headers=auth_b)
    assert r.status_code == 200
    src = r.json()
    assert src["rom_rel_path"] == "GBA/Pokemon Emerald.gba"
    assert src["console"] == "GBA"
    assert src["device_name"] == "Gaming PC"
    assert src["rom_path"] == "/mnt/nas/roms/GBA/Pokemon Emerald.gba"


@pytest.mark.asyncio
async def test_network_source_404_when_only_local(client):
    slug = await _add_game(client)
    await client.put(f"/games/{slug}/device", json={
        "rom_path": "/home/me/roms/g.gba", "save_path": "/saves/g.srm",
        "rom_source": "local", "rom_rel_path": "",
    }, headers=AUTH)
    r = await client.get(f"/games/{slug}/network-source", headers=_device_auth("dev-b", "Deck"))
    assert r.status_code == 404


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


def test_v28_to_v29_migration_adds_extra_folders(tmp_path):
    """A v28 consoles table gains device_extra_folders as '[]' without losing rows (#629)."""
    from server.store import schema

    conn = sqlite3.connect(str(tmp_path / "old.db"))
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE consoles (
        id TEXT PRIMARY KEY, device_id TEXT NOT NULL, console_name TEXT NOT NULL,
        shortform_name TEXT NOT NULL, device_game_folder TEXT NOT NULL DEFAULT '')""")
    conn.execute("INSERT INTO consoles VALUES ('c1', 'd1', 'GBA', 'gba', '/roms/gba')")
    conn.execute("PRAGMA user_version = 28")
    conn.commit()

    schema._migrate(conn, from_version=28)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == schema._SCHEMA_VERSION
    row = conn.execute("SELECT * FROM consoles").fetchone()
    assert row["device_game_folder"] == "/roms/gba"
    assert row["device_extra_folders"] == "[]"


# ── network share identity (#644) ────────────────────────────────────────────

async def _console_row(client, headers, slug):
    """Create the caller's GBA console row via a game config, return (device_id, row)."""
    await client.put(f"/games/{slug}/device", json={
        "rom_path": "/mnt/nas/GBA/g.gba", "save_path": "/saves/g.srm",
        "rom_folder_path": "/mnt/nas/GBA", "rom_source": "network",
        "device_network_folder": "/mnt/nas/GBA",
    }, headers=headers)
    dev = (await client.get("/whoami", headers=headers)).json()["device_id"]
    rows = (await client.get(f"/devices/{dev}/consoles", headers=headers)).json()
    return dev, next(c for c in rows if c["console_name"] == "GBA")


async def _set_share(client, headers, dev, row, share_id):
    body = {k: row.get(k, "") for k in (
        "device_game_folder", "device_save_folder", "device_state_folder",
        "device_emulator", "device_network_folder", "device_local_folder")}
    if share_id is not None:
        body["network_share_id"] = share_id
    r = await client.put(f"/devices/{dev}/consoles/{row['id']}", json=body, headers=headers)
    assert r.status_code == 200
    return (await client.get(f"/devices/{dev}/consoles", headers=headers)).json()


def test_v29_to_v30_migration_adds_share_id(tmp_path):
    """A v29 consoles table gains network_share_id as '' without losing rows (#644)."""
    from server.store import schema

    conn = sqlite3.connect(str(tmp_path / "old.db"))
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE consoles (
        id TEXT PRIMARY KEY, device_id TEXT NOT NULL, console_name TEXT NOT NULL,
        shortform_name TEXT NOT NULL, device_game_folder TEXT NOT NULL DEFAULT '')""")
    conn.execute("INSERT INTO consoles VALUES ('c1', 'd1', 'GBA', 'gba', '/roms/gba')")
    conn.execute("PRAGMA user_version = 29")
    conn.commit()

    schema._migrate(conn, from_version=29)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == schema._SCHEMA_VERSION
    row = conn.execute("SELECT * FROM consoles").fetchone()
    assert row["device_game_folder"] == "/roms/gba"
    assert row["network_share_id"] == ""


@pytest.mark.asyncio
async def test_console_put_stores_and_preserves_share_id(client):
    slug = await _add_game(client)
    dev, row = await _console_row(client, AUTH, slug)
    assert row["network_share_id"] == ""
    rows = await _set_share(client, AUTH, dev, row, "share-1")
    assert rows[0]["network_share_id"] == "share-1"
    # A PUT that omits the field keeps the stored ID.
    rows = await _set_share(client, AUTH, dev, rows[0], None)
    assert rows[0]["network_share_id"] == "share-1"


@pytest.mark.asyncio
async def test_console_shares_lists_other_devices_only(client):
    slug = await _add_game(client)
    other = _device_auth("dev-b", "steam-deck")
    dev_a, row_a = await _console_row(client, AUTH, slug)
    dev_b, row_b = await _console_row(client, other, slug)
    await _set_share(client, AUTH, dev_a, row_a, "share-1")
    await _set_share(client, other, dev_b, row_b, "share-1")

    r = await client.get("/consoles/GBA/shares", headers=AUTH)
    assert r.status_code == 200
    assert r.json() == [{"device_id": dev_b, "device_name": "steam-deck", "share_id": "share-1"}]


@pytest.mark.asyncio
async def test_console_shares_mismatch_and_blank(client):
    slug = await _add_game(client)
    other = _device_auth("dev-b", "steam-deck")
    dev_a, row_a = await _console_row(client, AUTH, slug)
    dev_b, row_b = await _console_row(client, other, slug)
    await _set_share(client, AUTH, dev_a, row_a, "share-1")

    # Device B has no share registered yet: omitted from A's view.
    assert (await client.get("/consoles/GBA/shares", headers=AUTH)).json() == []

    # B registers a different share: listed with its own ID so the client sees a mismatch.
    await _set_share(client, other, dev_b, row_b, "share-2")
    ids = [s["share_id"] for s in (await client.get("/consoles/GBA/shares", headers=AUTH)).json()]
    assert ids == ["share-2"]
    # Unknown console: empty list.
    assert (await client.get("/consoles/NOPE/shares", headers=AUTH)).json() == []


@pytest.mark.asyncio
async def test_cannot_edit_other_devices_console_share_id(client):
    slug = await _add_game(client)
    other = _device_auth("dev-b", "steam-deck")
    dev_b, row_b = await _console_row(client, other, slug)
    r = await client.put(f"/devices/{dev_b}/consoles/{row_b['id']}",
                         json={"network_share_id": "x"}, headers=AUTH)
    assert r.status_code == 403
