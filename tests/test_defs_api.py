"""API-level tests for the read-only definition routes (server/api/defs.py,
issue #364): /console-defs, /system-defs, /console-folder-names,
/standalones/{console_key}. Previously these had zero coverage through the
router — only indirect coverage of the underlying Store methods
(tests/test_store_internals.py) — so a regression in the API layer itself
(auth wiring, route registration, response shaping) had nothing to catch it.

These endpoints back the entire import wizard (GUI + CLI), including the
romExtensions-falling-back-to-systemKeys behavior PS2 import depends on
(issue #293) — the exact kind of regression issue #361 hit.
"""
from __future__ import annotations

import tempfile

import pytest
from httpx import ASGITransport, AsyncClient

from cli.consoles_data import _prepare_console_seed_data
from server import api as api_module
from server.store import Store
from tests.conftest import AUTH, MASTER_PIN


@pytest.fixture
async def seeded_client():
    """A real FastAPI app, seeded with the actual console defs (not a store
    fixture with hand-built rows) so these tests catch real regressions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        store.seed_console_defs(_prepare_console_seed_data())
        api_module.init(store, MASTER_PIN)
        async with AsyncClient(
            transport=ASGITransport(app=api_module.app),
            base_url="http://test",
        ) as c:
            yield c


@pytest.mark.asyncio
async def test_console_defs_requires_auth(client):
    r = await client.get("/console-defs")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_console_defs_ps2_reports_rom_extensions_not_system_keys(seeded_client):
    """The exact regression issue #361 hit: PS2 has no systemKeys, so the CLI
    wizard must read romExtensions instead — assert the API actually serves it."""
    r = await seeded_client.get("/console-defs", headers=AUTH)
    assert r.status_code == 200
    defs = {c["key"]: c for c in r.json()}
    ps2 = defs.get("ps2")
    assert ps2 is not None
    assert ps2["systemKeys"] == []
    assert set(ps2["romExtensions"]) == {"iso", "chd", "bin"}


@pytest.mark.asyncio
async def test_console_defs_falls_back_to_system_keys_when_no_rom_extensions(seeded_client):
    r = await seeded_client.get("/console-defs", headers=AUTH)
    assert r.status_code == 200
    defs = {c["key"]: c for c in r.json()}
    gba = defs["gba"]
    assert gba["romExtensions"] == gba["systemKeys"]
    assert "gba" in gba["romExtensions"]


@pytest.mark.asyncio
async def test_console_defs_include_databases(seeded_client):
    """Console defs carry the libretro database names the GUI's info-file core
    discovery matches against (#400)."""
    r = await seeded_client.get("/console-defs", headers=AUTH)
    assert r.status_code == 200
    defs = {c["key"]: c for c in r.json()}
    assert defs["snes"]["databases"] == ["Nintendo - Super Nintendo Entertainment System"]
    assert "Sega - Game Gear" in defs["sms"]["databases"]


@pytest.mark.asyncio
async def test_system_defs_requires_auth(client):
    r = await client.get("/system-defs")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_system_defs_returns_cores_keyed_by_extension(seeded_client):
    r = await seeded_client.get("/system-defs", headers=AUTH)
    assert r.status_code == 200
    defs = r.json()
    assert "gba" in defs
    assert defs["gba"]["name"] == "Game Boy Advance"
    assert any(c["lib"] == "mgba_libretro" for c in defs["gba"]["cores"])


@pytest.mark.asyncio
async def test_console_folder_names_requires_auth(client):
    r = await client.get("/console-folder-names")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_console_folder_names_returns_dict(seeded_client):
    r = await seeded_client.get("/console-folder-names", headers=AUTH)
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


@pytest.mark.asyncio
async def test_standalones_requires_auth(client):
    r = await client.get("/standalones/ps2")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_standalones_returns_pcsx2_for_ps2(seeded_client):
    r = await seeded_client.get("/standalones/ps2", headers=AUTH)
    assert r.status_code == 200
    standalones = r.json()
    labels = {s["label"] for s in standalones}
    assert "PCSX2" in labels
    pcsx2 = next(s for s in standalones if s["label"] == "PCSX2")
    assert pcsx2["launch_args"] == ["-batch", "-fullscreen"]
    assert pcsx2["dirs"]["native"]["state"].endswith("/sstates")


@pytest.mark.asyncio
async def test_standalones_unknown_console_returns_empty_list(seeded_client):
    r = await seeded_client.get("/standalones/does-not-exist", headers=AUTH)
    assert r.status_code == 200
    assert r.json() == []
