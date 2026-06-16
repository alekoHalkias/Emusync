"""ROM push transfers, pull requests, staging cleanup (#202), integrity (#214)."""
from __future__ import annotations

import hashlib
import tempfile

import pytest

from server import api as api_module
from server.store import Store
from tests.conftest import AUTH, MASTER_PIN, _device_auth


# ── rom transfers ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rom_transfer_queued(make_client, tmp_path):
    """Push a ROM file to the server; record is created as pending."""
    rom_file = tmp_path / "game.gba"
    rom_file.write_bytes(b"ROMDATA" * 100)

    c = await make_client(data_dir=str(tmp_path))
    auth_src = _device_auth("dev-src", "PC")
    auth_dst = _device_auth("dev-dst", "Steam Deck")

    # Register both devices and create a game
    await c.get("/health")
    await c.get("/games", headers=auth_src)
    await c.get("/games", headers=auth_dst)
    await c.post("/games", json={"name": "Metroid", "console": "GBA"}, headers=auth_src)

    # Push ROM transfer
    r = await c.post(
        "/games/metroid/rom-transfer",
        content=rom_file.read_bytes(),
        headers={
            **auth_src,
            "Content-Type": "application/octet-stream",
            "X-To-Device-ID": "dev-dst",
            "X-Destination-Path": "/home/deck/Games/GBA/Metroid.gba",
            "X-Filename": "Metroid.gba",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "pending"
    assert "transfer_id" in body

    # Staged file exists on disk (nested under transfer_id subdir)
    staging = tmp_path / "rom_staging"
    staged = list(staging.rglob("*.gba"))
    assert len(staged) == 1
    assert staged[0].name == "Metroid.gba"
    assert staged[0].read_bytes() == rom_file.read_bytes()


@pytest.mark.asyncio
async def test_rom_transfer_missing_game(make_client, tmp_path):
    """Transfer for a non-existent game returns 404."""
    c = await make_client(data_dir=str(tmp_path))
    auth_src = _device_auth("dev-src", "PC")
    auth_dst = _device_auth("dev-dst", "Deck")
    await c.get("/games", headers=auth_src)
    await c.get("/games", headers=auth_dst)

    r = await c.post(
        "/games/no-such-game/rom-transfer",
        content=b"data",
        headers={
            **auth_src,
            "Content-Type": "application/octet-stream",
            "X-To-Device-ID": "dev-dst",
            "X-Destination-Path": "/tmp/game.gba",
            "X-Filename": "game.gba",
        },
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_rom_transfer_missing_target(make_client, tmp_path):
    """Transfer to an unknown device ID returns 404."""
    c = await make_client(data_dir=str(tmp_path))
    auth_src = _device_auth("dev-src", "PC")
    await c.get("/games", headers=auth_src)
    await c.post("/games", json={"name": "Game"}, headers=auth_src)

    r = await c.post(
        "/games/game/rom-transfer",
        content=b"data",
        headers={
            **auth_src,
            "Content-Type": "application/octet-stream",
            "X-To-Device-ID": "ghost-device",
            "X-Destination-Path": "/tmp/game.gba",
            "X-Filename": "game.gba",
        },
    )
    assert r.status_code == 404


# ── rom pull request tests ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pull_request_queued(make_client, tmp_path):
    """POST /games/{slug}/rom-pull-request creates a pending request; source device can fetch it."""
    c = await make_client(data_dir=str(tmp_path))
    auth_src = _device_auth("src-device", "PC")
    auth_dst = _device_auth("dst-device", "Deck")

    await c.post("/games", json={"name": "Castlevania", "console": "GBA"}, headers=auth_src)
    await c.put("/games/castlevania/device", json={"rom_path": "/roms/Castlevania.gba"}, headers=auth_src)

    # Destination device sends a pull request
    r = await c.post(
        "/games/castlevania/rom-pull-request",
        json={"from_device_id": "src-device", "destination_path": "/home/deck/roms/Castlevania.gba"},
        headers=auth_dst,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "pending"
    assert "pull_request_id" in body
    assert "source_online" in body

    # Source device sees it in pending list
    r2 = await c.get("/rom-pull-requests/pending", headers=auth_src)
    assert r2.status_code == 200
    pending = r2.json()
    assert len(pending) == 1
    assert pending[0]["slug"] == "castlevania"
    assert pending[0]["to_device_id"] == "dst-device"
    assert pending[0]["destination_path"] == "/home/deck/roms/Castlevania.gba"
    assert pending[0]["game_name"] == "Castlevania"
    assert pending[0]["console"] == "GBA"


@pytest.mark.asyncio
async def test_pull_request_missing_game(client):
    """POST /games/{slug}/rom-pull-request returns 404 for unknown game."""
    auth_b = _device_auth("src-b", "PC")
    await client.post("/games", json={"name": "Temp"}, headers=AUTH)  # register src-b as device
    await client.get("/devices", headers=auth_b)

    r = await client.post(
        "/games/ghost-game/rom-pull-request",
        json={"from_device_id": "src-b", "destination_path": "/tmp/ghost.gba"},
        headers=AUTH,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_pull_request_missing_source_device(client):
    """POST /games/{slug}/rom-pull-request returns 404 for unknown source device."""
    await client.post("/games", json={"name": "Metroid"}, headers=AUTH)

    r = await client.post(
        "/games/metroid/rom-pull-request",
        json={"from_device_id": "ghost-device-999", "destination_path": "/tmp/metroid.gba"},
        headers=AUTH,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_pull_request_mark_fulfilled(make_client, tmp_path):
    """Source device can mark a pull request as fulfilled."""
    c = await make_client(data_dir=str(tmp_path))
    auth_src = _device_auth("src-ff", "PC")
    auth_dst = _device_auth("dst-ff", "Deck")

    await c.post("/games", json={"name": "Zelda", "console": "SNES"}, headers=auth_src)

    r = await c.post(
        "/games/zelda/rom-pull-request",
        json={"from_device_id": "src-ff", "destination_path": "/roms/Zelda.sfc"},
        headers=auth_dst,
    )
    pr_id = r.json()["pull_request_id"]

    # Source marks it fulfilled
    r2 = await c.put(f"/rom-pull-requests/{pr_id}", json={"status": "fulfilled"}, headers=auth_src)
    assert r2.status_code == 200

    # No longer shows as pending for source
    r3 = await c.get("/rom-pull-requests/pending", headers=auth_src)
    assert r3.json() == []


@pytest.mark.asyncio
async def test_pull_request_wrong_device_cannot_update(make_client, tmp_path):
    """A device that is not the source cannot mark a pull request as fulfilled."""
    c = await make_client(data_dir=str(tmp_path))
    auth_src = _device_auth("src-ww", "PC")
    auth_dst = _device_auth("dst-ww", "Deck")
    auth_third = _device_auth("third-ww", "Other")

    await c.post("/games", json={"name": "Mario"}, headers=auth_src)

    r = await c.post(
        "/games/mario/rom-pull-request",
        json={"from_device_id": "src-ww", "destination_path": "/roms/Mario.sfc"},
        headers=auth_dst,
    )
    pr_id = r.json()["pull_request_id"]

    # Third party cannot update it
    r2 = await c.put(f"/rom-pull-requests/{pr_id}", json={"status": "fulfilled"}, headers=auth_third)
    assert r2.status_code == 403


# ── staged-file cleanup (#202) ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_completed_transfer_removes_staged_file(make_client, tmp_path):
    """Marking a transfer completed must reclaim its staging directory."""
    rom_file = tmp_path / "game.gba"
    rom_file.write_bytes(b"ROMDATA" * 100)

    c = await make_client(data_dir=str(tmp_path))
    auth_src = _device_auth("dev-src", "PC")
    auth_dst = _device_auth("dev-dst", "Deck")
    await c.get("/games", headers=auth_src)
    await c.get("/games", headers=auth_dst)
    await c.post("/games", json={"name": "Metroid", "console": "GBA"}, headers=auth_src)

    r = await c.post(
        "/games/metroid/rom-transfer",
        content=rom_file.read_bytes(),
        headers={
            **auth_src,
            "Content-Type": "application/octet-stream",
            "X-To-Device-ID": "dev-dst",
            "X-Destination-Path": "/home/deck/Games/GBA/Metroid.gba",
            "X-Filename": "Metroid.gba",
        },
    )
    transfer_id = r.json()["transfer_id"]
    staging_subdir = tmp_path / "rom_staging" / transfer_id
    assert staging_subdir.exists()

    # Receiver marks it completed → staged file is reclaimed.
    r = await c.put(
        f"/rom-transfers/{transfer_id}",
        json={"status": "completed"},
        headers=auth_dst,
    )
    assert r.status_code == 200
    assert not staging_subdir.exists()


def test_startup_sweep_removes_orphan_staging(tmp_path):
    """init() must drop staging dirs that have no matching pending transfer."""
    staging_root = tmp_path / "rom_staging"
    orphan = staging_root / "ghost-transfer"
    orphan.mkdir(parents=True)
    (orphan / "leftover.gba").write_bytes(b"junk")

    with tempfile.TemporaryDirectory() as db_dir:
        store = Store(db_dir)
        api_module.init(store, MASTER_PIN, str(tmp_path))
        assert not orphan.exists()


# ── ROM transfer integrity (issue #214) ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_rom_transfer_records_and_serves_sha256(make_client, tmp_path):
    rom_bytes = b"ROMDATA" * 500
    expected = hashlib.sha256(rom_bytes).hexdigest()

    c = await make_client(data_dir=str(tmp_path))
    auth_src = _device_auth("dev-src", "PC")
    auth_dst = _device_auth("dev-dst", "Deck")
    await c.get("/games", headers=auth_src)
    await c.get("/games", headers=auth_dst)
    await c.post("/games", json={"name": "Metroid", "console": "GBA"}, headers=auth_src)

    r = await c.post(
        "/games/metroid/rom-transfer",
        content=rom_bytes,
        headers={
            **auth_src,
            "Content-Type": "application/octet-stream",
            "X-To-Device-ID": "dev-dst",
            "X-Destination-Path": "/home/deck/Games/GBA/Metroid.gba",
            "X-Filename": "Metroid.gba",
        },
    )
    transfer_id = r.json()["transfer_id"]

    # Pending list surfaces the hash so the receiver can verify.
    pending = (await c.get("/rom-transfers/pending", headers=auth_dst)).json()
    assert pending[0]["sha256"] == expected

    # Download response carries the hash header.
    dl = await c.get(f"/rom-transfers/{transfer_id}/file", headers=auth_dst)
    assert dl.status_code == 200
    assert dl.headers["x-rom-hash"] == expected
    assert hashlib.sha256(dl.content).hexdigest() == expected
