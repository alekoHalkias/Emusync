"""
ROM import integration tests for EmuSync.

Tests the full workflow of scanning test ROMs, importing them into the game list,
listing the imported games, and then deleting them. Covers GBA, GB, and SNES consoles.

Run:  .venv/bin/python -m pytest tests/test_rom_import.py -v
      or just: .venv/bin/python -m pytest tests/ -v
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import AUTH

# Path to test ROM folder (relative to repo root)
TEST_ROM_BASE = Path(__file__).parent.parent / "test_rom_folders"

# Test ROM definitions: (console, folder, expected_roms)
# Each console has 2 test ROMs to import
TEST_CONSOLES = {
    "gba": {
        "path": TEST_ROM_BASE / "gba",
        "roms": [
            {"file": "test.gba", "name": "test"},
            {"file": "test2/test2.gba", "name": "test2"},
        ],
    },
    "gb": {
        "path": TEST_ROM_BASE / "gbc",
        "roms": [
            {"file": "test.gb", "name": "test"},
            {"file": "test2/test.gb", "name": "test"},  # Same name in diff folder
        ],
    },
    "snes": {
        "path": TEST_ROM_BASE / "snes",
        "roms": [
            {"file": "test.sfc", "name": "test"},
            {"file": "test2/test2.sfc", "name": "test2"},
        ],
    },
}


@pytest.mark.asyncio
async def test_scan_gba_roms(client):
    """Test 1a: Scan GBA test ROMs from CLI-accessible folder (skipped if test ROMs not present)."""
    auth = AUTH

    gba_path = TEST_CONSOLES["gba"]["path"]
    if not gba_path.exists():
        pytest.skip(f"GBA test ROM folder not found: {gba_path}")

    # Verify the test ROMs exist
    for rom_def in TEST_CONSOLES["gba"]["roms"]:
        rom_file = gba_path / rom_def["file"]
        assert rom_file.exists(), f"Test ROM not found: {rom_file}"


@pytest.mark.asyncio
async def test_scan_gb_roms(client):
    """Test 1b: Scan GB test ROMs from CLI-accessible folder (skipped if test ROMs not present)."""
    auth = AUTH

    gb_path = TEST_CONSOLES["gb"]["path"]
    if not gb_path.exists():
        pytest.skip(f"GB test ROM folder not found: {gb_path}")

    # Verify the test ROMs exist
    for rom_def in TEST_CONSOLES["gb"]["roms"]:
        rom_file = gb_path / rom_def["file"]
        assert rom_file.exists(), f"Test ROM not found: {rom_file}"


@pytest.mark.asyncio
async def test_scan_snes_roms(client):
    """Test 1c: Scan SNES test ROMs from CLI-accessible folder (skipped if test ROMs not present)."""
    auth = AUTH

    snes_path = TEST_CONSOLES["snes"]["path"]
    if not snes_path.exists():
        pytest.skip(f"SNES test ROM folder not found: {snes_path}")

    # Verify the test ROMs exist
    for rom_def in TEST_CONSOLES["snes"]["roms"]:
        rom_file = snes_path / rom_def["file"]
        assert rom_file.exists(), f"Test ROM not found: {rom_file}"


@pytest.mark.asyncio
async def test_import_all_test_roms(client):
    """Test 2: Import all 6 test ROMs (2 per console: GBA, GB, SNES)."""
    auth = AUTH

    imported_games = []

    # Import GBA ROMs
    for i, rom_def in enumerate(TEST_CONSOLES["gba"]["roms"]):
        rom_path = TEST_CONSOLES["gba"]["path"] / rom_def["file"]
        game_name = f"GBA-test-{i+1}"
        r = await client.post("/games", json={"name": game_name}, headers=auth)
        assert r.status_code == 200
        slug = r.json()["slug"]
        imported_games.append(slug)

        # Set device config for the ROM
        r = await client.put(f"/games/{slug}/device", json={
            "rom_path": str(rom_path),
            "save_path": str(rom_path.parent / f"{rom_def['name']}.sav"),
            "launch_command": f"retroarch -L mgba.so {rom_path}",
        }, headers=auth)
        assert r.status_code == 200

    # Import GB ROMs
    for i, rom_def in enumerate(TEST_CONSOLES["gb"]["roms"]):
        rom_path = TEST_CONSOLES["gb"]["path"] / rom_def["file"]
        game_name = f"GB-test-{i+1}"
        r = await client.post("/games", json={"name": game_name}, headers=auth)
        assert r.status_code == 200
        slug = r.json()["slug"]
        imported_games.append(slug)

        # Set device config for the ROM
        r = await client.put(f"/games/{slug}/device", json={
            "rom_path": str(rom_path),
            "save_path": str(rom_path.parent / f"{rom_def['name']}.sav"),
            "launch_command": f"retroarch -L gambatte.so {rom_path}",
        }, headers=auth)
        assert r.status_code == 200

    # Import SNES ROMs
    for i, rom_def in enumerate(TEST_CONSOLES["snes"]["roms"]):
        rom_path = TEST_CONSOLES["snes"]["path"] / rom_def["file"]
        game_name = f"SNES-test-{i+1}"
        r = await client.post("/games", json={"name": game_name}, headers=auth)
        assert r.status_code == 200
        slug = r.json()["slug"]
        imported_games.append(slug)

        # Set device config for the ROM
        r = await client.put(f"/games/{slug}/device", json={
            "rom_path": str(rom_path),
            "save_path": str(rom_path.parent / f"{rom_def['name']}.srm"),
            "launch_command": f"retroarch -L snes9x.so {rom_path}",
        }, headers=auth)
        assert r.status_code == 200

    # Store for use in next test
    assert len(imported_games) == 6, f"Expected 6 imported games, got {len(imported_games)}"


@pytest.mark.asyncio
async def test_list_all_imported_roms(client):
    """Test 3: List all 6 imported games and verify they appear."""
    auth = AUTH

    # First, import all the test ROMs
    imported_slugs = []

    # Import GBA ROMs
    for i, rom_def in enumerate(TEST_CONSOLES["gba"]["roms"]):
        rom_path = TEST_CONSOLES["gba"]["path"] / rom_def["file"]
        game_name = f"GBA-test-{i+1}"
        r = await client.post("/games", json={"name": game_name}, headers=auth)
        assert r.status_code == 200
        slug = r.json()["slug"]
        imported_slugs.append(slug)
        await client.put(f"/games/{slug}/device", json={
            "rom_path": str(rom_path),
            "save_path": str(rom_path.parent / f"{rom_def['name']}.sav"),
            "launch_command": f"retroarch -L mgba.so {rom_path}",
        }, headers=auth)

    # Import GB ROMs
    for i, rom_def in enumerate(TEST_CONSOLES["gb"]["roms"]):
        rom_path = TEST_CONSOLES["gb"]["path"] / rom_def["file"]
        game_name = f"GB-test-{i+1}"
        r = await client.post("/games", json={"name": game_name}, headers=auth)
        assert r.status_code == 200
        slug = r.json()["slug"]
        imported_slugs.append(slug)
        await client.put(f"/games/{slug}/device", json={
            "rom_path": str(rom_path),
            "save_path": str(rom_path.parent / f"{rom_def['name']}.sav"),
            "launch_command": f"retroarch -L gambatte.so {rom_path}",
        }, headers=auth)

    # Import SNES ROMs
    for i, rom_def in enumerate(TEST_CONSOLES["snes"]["roms"]):
        rom_path = TEST_CONSOLES["snes"]["path"] / rom_def["file"]
        game_name = f"SNES-test-{i+1}"
        r = await client.post("/games", json={"name": game_name}, headers=auth)
        assert r.status_code == 200
        slug = r.json()["slug"]
        imported_slugs.append(slug)
        await client.put(f"/games/{slug}/device", json={
            "rom_path": str(rom_path),
            "save_path": str(rom_path.parent / f"{rom_def['name']}.srm"),
            "launch_command": f"retroarch -L snes9x.so {rom_path}",
        }, headers=auth)

    # Now list all games and verify all 6 are present
    r = await client.get("/games", headers=auth)
    assert r.status_code == 200
    games = r.json()
    game_slugs = [g["slug"] for g in games]

    assert len(games) == 6, f"Expected 6 games in list, got {len(games)}"
    for slug in imported_slugs:
        assert slug in game_slugs, f"Game {slug} not found in game list"


@pytest.mark.asyncio
async def test_delete_all_imported_roms(client):
    """Test 4: Delete all 6 imported games and verify they are gone."""
    auth = AUTH

    # First, import all the test ROMs
    imported_slugs = []

    # Import GBA ROMs
    for i, rom_def in enumerate(TEST_CONSOLES["gba"]["roms"]):
        rom_path = TEST_CONSOLES["gba"]["path"] / rom_def["file"]
        game_name = f"GBA-test-{i+1}"
        r = await client.post("/games", json={"name": game_name}, headers=auth)
        slug = r.json()["slug"]
        imported_slugs.append(slug)
        await client.put(f"/games/{slug}/device", json={
            "rom_path": str(rom_path),
            "save_path": str(rom_path.parent / f"{rom_def['name']}.sav"),
            "launch_command": f"retroarch -L mgba.so {rom_path}",
        }, headers=auth)

    # Import GB ROMs
    for i, rom_def in enumerate(TEST_CONSOLES["gb"]["roms"]):
        rom_path = TEST_CONSOLES["gb"]["path"] / rom_def["file"]
        game_name = f"GB-test-{i+1}"
        r = await client.post("/games", json={"name": game_name}, headers=auth)
        slug = r.json()["slug"]
        imported_slugs.append(slug)
        await client.put(f"/games/{slug}/device", json={
            "rom_path": str(rom_path),
            "save_path": str(rom_path.parent / f"{rom_def['name']}.sav"),
            "launch_command": f"retroarch -L gambatte.so {rom_path}",
        }, headers=auth)

    # Import SNES ROMs
    for i, rom_def in enumerate(TEST_CONSOLES["snes"]["roms"]):
        rom_path = TEST_CONSOLES["snes"]["path"] / rom_def["file"]
        game_name = f"SNES-test-{i+1}"
        r = await client.post("/games", json={"name": game_name}, headers=auth)
        slug = r.json()["slug"]
        imported_slugs.append(slug)
        await client.put(f"/games/{slug}/device", json={
            "rom_path": str(rom_path),
            "save_path": str(rom_path.parent / f"{rom_def['name']}.srm"),
            "launch_command": f"retroarch -L snes9x.so {rom_path}",
        }, headers=auth)

    # Verify all 6 are present
    r = await client.get("/games", headers=auth)
    games = r.json()
    assert len(games) == 6, f"Expected 6 games before deletion, got {len(games)}"

    # Delete all imported games
    for slug in imported_slugs:
        r = await client.delete(f"/games/{slug}", headers=auth)
        assert r.status_code == 200

    # Verify all games are gone
    r = await client.get("/games", headers=auth)
    assert r.status_code == 200
    games = r.json()
    assert len(games) == 0, f"Expected 0 games after deletion, got {len(games)}"
