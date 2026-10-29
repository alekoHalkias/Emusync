"""Re-link flow behind the GUI's Refresh locations / broken-ROM prompt (#616).

The renderer does GET /games/{slug}/device then PUT with rom_path replaced
(useBrokenRoms.ts); these tests pin that round-trip on real SQLite.
"""
from __future__ import annotations

import pytest

from tests.conftest import AUTH, _device_auth


async def _relink(client, slug: str, new_rom: str, headers=AUTH) -> dict:
    cfg = (await client.get(f"/games/{slug}/device", headers=headers)).json()
    cfg["rom_path"] = new_rom
    r = await client.put(f"/games/{slug}/device", json=cfg, headers=headers)
    assert r.status_code == 200
    return (await client.get(f"/games/{slug}/device", headers=headers)).json()


@pytest.mark.asyncio
async def test_relink_updates_rom_path_and_preserves_other_fields(client):
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=AUTH)
    cfg = {
        "rom_path": "/old/emerald.gba",
        "save_path": "/saves/emerald.srm",
        "state_path": "/states/emerald",
        "rom_folder_path": "/old",
        "launch_command": "retroarch -L mgba.so %ROM%",
    }
    await client.put("/games/pokemon-emerald/device", json=cfg, headers=AUTH)

    got = await _relink(client, "pokemon-emerald", "/new/emerald.gba")

    assert got["rom_path"] == "/new/emerald.gba"
    for k in ("save_path", "state_path", "rom_folder_path", "launch_command"):
        assert got[k] == cfg[k]


@pytest.mark.asyncio
async def test_relink_switch_folder_rom(client):
    await client.post("/games", json={"name": "Zelda", "console": "switch"}, headers=AUTH)
    await client.put("/games/zelda/device", json={
        "rom_path": "/old/Zelda", "save_path": "", "launch_command": "eden %ROM%",
    }, headers=AUTH)

    assert (await _relink(client, "zelda", "/new/Zelda"))["rom_path"] == "/new/Zelda"


@pytest.mark.asyncio
async def test_relink_keeps_network_source(client):
    await client.post("/games", json={"name": "Kirby"}, headers=AUTH)
    await client.put("/games/kirby/device", json={
        "rom_path": "/mnt/nas/kirby.gba", "save_path": "", "launch_command": "",
        "rom_source": "network", "rom_rel_path": "gba/kirby.gba",
    }, headers=AUTH)

    got = await _relink(client, "kirby", "/mnt/nas2/kirby.gba")

    assert got["rom_path"] == "/mnt/nas2/kirby.gba"
    assert got["rom_source"] == "network"
    assert got["rom_rel_path"] == "gba/kirby.gba"


@pytest.mark.asyncio
async def test_relink_does_not_touch_other_device(client):
    await client.post("/games", json={"name": "Metroid"}, headers=AUTH)
    other = _device_auth("dev-b", "Other")
    for h, rom in ((AUTH, "/a/metroid.gba"), (other, "/b/metroid.gba")):
        await client.put("/games/metroid/device", json={
            "rom_path": rom, "save_path": "", "launch_command": "",
        }, headers=h)

    await _relink(client, "metroid", "/a2/metroid.gba")

    r = await client.get("/games/metroid/device", headers=other)
    assert r.json()["rom_path"] == "/b/metroid.gba"
