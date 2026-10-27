"""Save/state integrity classifier + recovery endpoints (issue #285).

The classifier flags a *current* blob as damaged when it is 0-byte, shrank below
50% of the prior generation, or no longer hashes to its recorded value. Verdicts
are computed from data already on disk + in the rows, so there is no migration.
"""
from __future__ import annotations

import hashlib
import tempfile

import pytest

from server.store import Store
from server.api import _core
from tests.conftest import AUTH, MASTER_PIN
from server import api as api_module


# ── helpers ─────────────────────────────────────────────────────────────────────

def _corrupt_current(store: Store, table: str, slug: str, data: bytes) -> None:
    """Overwrite the on-disk bytes of a game's current blob without touching the
    row's recorded hash/size — simulating crash damage / bit-rot."""
    row = store._newest_row(table, slug)
    store._blob_path(table, row["id"]).write_bytes(data)


# ── store-level classifier ───────────────────────────────────────────────────────

def test_integrity_ok_for_healthy_save():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(tmp)
        store.ensure_device("dev-1", "PC")
        store.add_game("zelda", "Zelda")
        store.push_save("zelda", "dev-1", b"a healthy save")
        verdict = store.integrity_for_game("zelda")["save"]
        assert verdict["status"] == "ok"
        assert verdict["reasons"] == []


def test_integrity_missing_when_no_blob():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(tmp)
        store.ensure_device("dev-1", "PC")
        store.add_game("zelda", "Zelda")
        verdict = store.integrity_for_game("zelda")["save"]
        assert verdict["status"] == "missing"
        assert verdict["last_good_version_id"] is None


def test_integrity_zero_byte():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(tmp)
        store.ensure_device("dev-1", "PC")
        store.add_game("zelda", "Zelda")
        store.push_save("zelda", "dev-1", b"real content here")
        _corrupt_current(store, "saves", "zelda", b"")
        verdict = store.integrity_for_game("zelda")["save"]
        assert verdict["status"] == "damaged"
        assert "zero_byte" in verdict["reasons"]


def test_integrity_shrank():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(tmp)
        store.ensure_device("dev-1", "PC")
        store.add_game("zelda", "Zelda")
        store.push_save("zelda", "dev-1", b"x" * 1000)       # prior generation
        store.push_save("zelda", "dev-1", b"y" * 800)        # current (distinct)
        _corrupt_current(store, "saves", "zelda", b"z" * 100)  # < 50% of 1000
        verdict = store.integrity_for_game("zelda")["save"]
        assert verdict["status"] == "damaged"
        assert "shrank" in verdict["reasons"]


def test_integrity_hash_mismatch():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(tmp)
        store.ensure_device("dev-1", "PC")
        store.add_game("zelda", "Zelda")
        store.push_save("zelda", "dev-1", b"original-bytes")
        # Same length, different content → only the hash changes.
        _corrupt_current(store, "saves", "zelda", b"swapped--bytes")
        verdict = store.integrity_for_game("zelda")["save"]
        assert verdict["status"] == "damaged"
        assert "hash_mismatch" in verdict["reasons"]


def test_integrity_last_good_version_points_at_prior_healthy():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(tmp)
        store.ensure_device("dev-1", "PC")
        store.add_game("zelda", "Zelda")
        store.push_save("zelda", "dev-1", b"good-generation-one")
        good_id = store._newest_row("saves", "zelda")["id"]
        store.push_save("zelda", "dev-1", b"good-generation-two")
        _corrupt_current(store, "saves", "zelda", b"corrupted-gen-two!!")  # same length
        verdict = store.integrity_for_game("zelda")["save"]
        assert verdict["status"] == "damaged"
        assert verdict["last_good_version_id"] == good_id


def test_sweep_skips_games_without_blobs():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(tmp)
        store.ensure_device("dev-1", "PC")
        store.add_game("zelda", "Zelda")
        store.add_game("metroid", "Metroid")  # no blobs
        store.push_save("zelda", "dev-1", b"some save")
        swept = store.sweep_integrity()
        assert "zelda" in swept
        assert "metroid" not in swept


def test_integrity_state_zero_byte():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(tmp)
        store.ensure_device("dev-1", "PC")
        store.add_game("zelda", "Zelda")
        store.push_state("zelda", "dev-1", b"a state archive blob")
        _corrupt_current(store, "states", "zelda", b"")
        verdict = store.integrity_for_game("zelda")["state"]
        assert verdict["status"] == "damaged"
        assert "zero_byte" in verdict["reasons"]


# ── API endpoints ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_integrity_endpoint_healthy(client):
    await client.post("/games", json={"name": "Zelda"}, headers=AUTH)
    await client.post("/games/zelda/save", content=b"a healthy save", headers=AUTH)
    r = await client.get("/games/zelda/integrity", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["save"]["status"] == "ok"
    assert r.json()["state"]["status"] == "missing"


@pytest.mark.asyncio
async def test_get_integrity_endpoint_404(client):
    r = await client.get("/games/ghost/integrity", headers=AUTH)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_integrity_endpoint_damaged(client):
    await client.post("/games", json={"name": "Zelda"}, headers=AUTH)
    await client.post("/games/zelda/save", content=b"good-bytes-one", headers=AUTH)
    await client.post("/games/zelda/save", content=b"good-bytes-two", headers=AUTH)
    _corrupt_current(_core._get_store(), "saves", "zelda", b"")

    r = await client.get("/games/zelda/integrity", headers=AUTH)
    assert r.status_code == 200
    save = r.json()["save"]
    assert save["status"] == "damaged"
    assert "zero_byte" in save["reasons"]
    assert save["last_good_version_id"]  # a prior healthy generation exists


@pytest.mark.asyncio
async def test_integrity_requires_auth(client):
    await client.post("/games", json={"name": "Zelda"}, headers=AUTH)
    r = await client.get("/games/zelda/integrity")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_rescan_endpoint_reports_damaged(client):
    await client.post("/games", json={"name": "Zelda"}, headers=AUTH)
    await client.post("/games/zelda/save", content=b"healthy-content", headers=AUTH)
    _corrupt_current(_core._get_store(), "saves", "zelda", b"")

    r = await client.post("/integrity/rescan", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["scanned"] >= 1
    damaged = {(d["slug"], d["kind"]) for d in body["damaged"]}
    assert ("zelda", "save") in damaged


@pytest.mark.asyncio
async def test_restore_last_good_clears_damage(client):
    await client.post("/games", json={"name": "Zelda"}, headers=AUTH)
    await client.post("/games/zelda/save", content=b"good-save-bytes", headers=AUTH)
    await client.post("/games/zelda/save", content=b"newer-save-byte", headers=AUTH)
    _corrupt_current(_core._get_store(), "saves", "zelda", b"")

    before = (await client.get("/games/zelda/integrity", headers=AUTH)).json()["save"]
    assert before["status"] == "damaged"

    r = await client.post(
        "/games/zelda/save/restore",
        json={"version_id": before["last_good_version_id"]},
        headers=AUTH,
    )
    assert r.status_code == 200

    after = (await client.get("/games/zelda/integrity", headers=AUTH)).json()["save"]
    assert after["status"] == "ok"


def test_init_runs_sweep():
    """Startup sweep populates the at-rest snapshot with damaged games."""
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(tmp)
        store.ensure_device("dev-1", "PC")
        store.add_game("zelda", "Zelda")
        store.push_save("zelda", "dev-1", b"content-to-corrupt")
        _corrupt_current(store, "saves", "zelda", b"")

        api_module.init(store, MASTER_PIN)
        status = _core.get_integrity_status()
        assert "zelda" in status
        assert status["zelda"]["save"]["status"] == "damaged"
