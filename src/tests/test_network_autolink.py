"""GET /games/network-link-candidates: network games a device can link from its
own mount of the same share (issue #729). Real SQLite, no mocks."""
import pytest

from server.api import _core
from tests.conftest import AUTH, _device_auth
from tests.test_network_rom import _add_game, _console_row, _set_share

URL = "/games/network-link-candidates"
B = _device_auth("dev-b", "steam-deck")


async def _network_game(client, headers, slug, name="Pokemon Emerald", **over):
    """Write A's network config for *slug* (a PUT replaces the whole row)."""
    body = {
        "rom_path": f"/mnt/nas/GBA/{name}.gba", "save_path": f"/home/a/saves/{name}/{name}.srm",
        "state_path": "", "launch_command": f"retroarch '/mnt/nas/GBA/{name}.gba'",
        "rom_folder_path": "/mnt/nas/GBA", "rom_source": "network",
        "rom_rel_path": f"GBA/{name}.gba", "device_network_folder": "/mnt/nas/GBA",
    }
    body.update(over)
    assert (await client.put(f"/games/{slug}/device", json=body, headers=headers)).status_code == 200


async def _setup(client, share_a="share-1", share_b="share-1", **game_over):
    """A has a network game; B has a GBA console (via another game) on its own mount."""
    slug = await _add_game(client)
    dev_a, row_a = await _console_row(client, AUTH, slug)
    dev_b, row_b = await _console_row(client, B, await _add_game(client, "B Only"))
    await _set_share(client, AUTH, dev_a, row_a, share_a)
    row_b["device_network_folder"] = "/media/deck/nas"
    await _set_share(client, B, dev_b, row_b, share_b)
    await _network_game(client, AUTH, slug, **game_over)
    return slug


async def _slugs(client, headers):
    r = await client.get(URL, headers=headers)
    assert r.status_code == 200
    return [c["slug"] for c in r.json()]


@pytest.mark.asyncio
async def test_matching_share_lists_game_with_own_mount(client):
    slug = await _setup(client)
    r = await client.get(URL, headers=B)
    assert r.status_code == 200
    rows = r.json()
    assert [c["slug"] for c in rows] == [slug]
    c = rows[0]
    assert set(c) == {"slug", "console", "rom_path", "rom_rel_path", "launch_command",
                      "save_path", "state_path", "share_id", "mount_root",
                      "rom_size", "match", "filename"}
    assert c["match"] == "exact" and c["filename"] == "Pokemon Emerald.gba"
    assert c["mount_root"] == "/media/deck/nas"
    assert c["rom_rel_path"] == "GBA/Pokemon Emerald.gba"
    assert c["launch_command"] == "retroarch '/mnt/nas/GBA/Pokemon Emerald.gba'"
    assert c["share_id"] == "share-1"


@pytest.mark.asyncio
async def test_share_mismatch_not_listed(client):
    slug = await _setup(client, share_b="share-2")
    assert slug not in await _slugs(client, B)


@pytest.mark.asyncio
@pytest.mark.parametrize("share_a,share_b", [("", "share-1"), ("share-1", "")])
async def test_blank_share_not_listed(client, share_a, share_b):
    slug = await _setup(client, share_a=share_a, share_b=share_b)
    assert slug not in await _slugs(client, B)


@pytest.mark.asyncio
async def test_already_configured_not_listed(client):
    slug = await _setup(client)
    await client.put(f"/games/{slug}/device", json={
        "rom_path": "/home/deck/g.gba", "save_path": "/s/g.srm", "rom_source": "local",
    }, headers=B)
    assert slug not in await _slugs(client, B)


@pytest.mark.asyncio
async def test_own_game_not_listed(client):
    slug = await _setup(client)
    assert slug not in await _slugs(client, AUTH)


@pytest.mark.asyncio
@pytest.mark.parametrize("over", [{"rom_source": "local"}, {"rom_rel_path": ""}])
async def test_local_or_relless_source_not_listed(client, over):
    slug = await _setup(client, **over)
    assert slug not in await _slugs(client, B)


@pytest.mark.asyncio
async def test_two_matching_console_rows_one_candidate(client):
    slug = await _setup(client)
    # A second GBA console row for B (different game folder) on the same share.
    store = _core._get_store()
    dev_b = (await client.get("/whoami", headers=B)).json()["device_id"]
    store._conn.execute(
        """INSERT INTO consoles (id, device_id, console_name, shortform_name, device_game_folder,
                                 device_network_folder, network_share_id)
           VALUES ('c-extra', ?, 'GBA', 'gba', '/other/roms', '/media/deck/nas2', 'share-1')""",
        (dev_b,),
    )
    store._conn.commit()
    assert (await _slugs(client, B)).count(slug) == 1


@pytest.mark.asyncio
async def test_blank_own_network_folder_not_listed(client):
    slug = await _add_game(client)
    dev_a, row_a = await _console_row(client, AUTH, slug)
    dev_b, row_b = await _console_row(client, B, await _add_game(client, "B Only"))
    await _set_share(client, AUTH, dev_a, row_a, "share-1")
    row_b["device_network_folder"] = ""
    await _set_share(client, B, dev_b, row_b, "share-1")
    await _network_game(client, AUTH, slug)
    assert slug not in await _slugs(client, B)


# ── fuzzy candidates (#731) ───────────────────────────────────────────────────
# Without a share-ID match a network game with a known size is still listed, as
# `match: "fuzzy"`, so the client can look for the same filename + size under its
# own mount and ask the user. The share tests above seed size 0 and stay unlisted.

async def _rows(client, headers):
    r = await client.get(URL, headers=headers)
    assert r.status_code == 200
    return {c["slug"]: c for c in r.json()}


@pytest.mark.asyncio
@pytest.mark.parametrize("share_a,share_b", [("share-1", "share-2"), ("", "share-1"), ("share-1", "")])
async def test_fuzzy_listed_without_share_match_when_size_known(client, share_a, share_b):
    slug = await _setup(client, share_a=share_a, share_b=share_b, rom_size=4096)
    c = (await _rows(client, B))[slug]
    assert c["match"] == "fuzzy"
    assert c["filename"] == "Pokemon Emerald.gba" and c["rom_size"] == 4096
    assert c["mount_root"] == "/media/deck/nas"


@pytest.mark.asyncio
async def test_fuzzy_not_listed_without_size(client):
    slug = await _setup(client, share_b="share-2")
    assert slug not in await _rows(client, B)


@pytest.mark.asyncio
async def test_fuzzy_not_listed_without_own_network_folder(client):
    slug = await _add_game(client)
    dev_a, row_a = await _console_row(client, AUTH, slug)
    dev_b, row_b = await _console_row(client, B, await _add_game(client, "B Only"))
    row_b["device_network_folder"] = ""
    await _set_share(client, B, dev_b, row_b, "")
    await _network_game(client, AUTH, slug, rom_size=4096)
    assert slug not in await _rows(client, B)


@pytest.mark.asyncio
async def test_fuzzy_not_listed_when_configured(client):
    slug = await _setup(client, share_b="share-2", rom_size=4096)
    await client.put(f"/games/{slug}/device", json={
        "rom_path": "/home/deck/g.gba", "save_path": "/s/g.srm", "rom_source": "local",
    }, headers=B)
    assert slug not in await _rows(client, B)


@pytest.mark.asyncio
async def test_exact_wins_over_fuzzy(client):
    slug = await _setup(client, rom_size=4096)
    rows = (await client.get(URL, headers=B)).json()
    assert [c["slug"] for c in rows].count(slug) == 1
    assert next(c for c in rows if c["slug"] == slug)["match"] == "exact"
