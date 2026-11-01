"""Regression tests for #701: upload/staging leaks and game check on push."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from server import api as api_module
from server.api import _core
from server.store import Store
from tests.conftest import AUTH, MASTER_PIN


def _uploads(store) -> list:
    d = store._blob_dir / ".uploads"
    return [p for p in d.iterdir()] if d.exists() else []


@pytest.mark.asyncio
@pytest.mark.parametrize("noun", ["save", "state"])
async def test_push_unknown_game_404_and_stages_nothing(client, noun):
    r = await client.post(f"/games/nope/{noun}", content=b"DATA", headers=AUTH)
    assert r.status_code == 404
    assert _uploads(_core._store) == []


@pytest.mark.asyncio
async def test_push_known_game_still_works(client):
    await client.post("/games", json={"name": "Metroid", "console": "GBA"}, headers=AUTH)
    r = await client.post("/games/metroid/save", content=b"DATA", headers=AUTH)
    assert r.status_code == 200
    assert _uploads(_core._store) == []


@pytest.mark.asyncio
async def test_store_failure_removes_staged_upload(client, monkeypatch):
    await client.post("/games", json={"name": "Metroid", "console": "GBA"}, headers=AUTH)

    def boom(self, *a, **k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(Store, "push_save_file", boom)
    with pytest.raises(RuntimeError):
        await client.post("/games/metroid/save", content=b"DATA", headers=AUTH)
    assert _uploads(_core._store) == []


@pytest.mark.asyncio
async def test_identical_memcard_push_leaves_no_staged_file(client):
    for _ in range(2):
        r = await client.post("/consoles/PS2/memcard", content=b"CARD", headers=AUTH)
        assert r.status_code == 200
    assert _uploads(_core._store) == []


def _transfer(store, tid, data_dir, queued_at):
    sub = data_dir / "rom_staging" / tid
    sub.mkdir(parents=True)
    (sub / "rom.bin").write_bytes(b"x")
    store.create_rom_transfer(tid, "g", "a", "b", "", str(sub / "rom.bin"))
    store._conn.execute("UPDATE rom_transfers SET queued_at = ? WHERE id = ?", (queued_at, tid))
    store._conn.commit()
    return sub


def test_init_sweeps_old_pending_transfers_only(tmp_path):
    store = Store(str(tmp_path / "db"))
    data_dir = tmp_path / "data"
    store._conn.execute("PRAGMA foreign_keys = OFF")
    old = (datetime.now(timezone.utc) - timedelta(days=_core._STAGING_MAX_AGE_DAYS + 1)).isoformat()
    new = datetime.now(timezone.utc).isoformat()
    old_dir = _transfer(store, "old", data_dir, old)
    new_dir = _transfer(store, "new", data_dir, new)
    api_module.init(store, MASTER_PIN, str(data_dir))
    assert not old_dir.exists()
    assert new_dir.exists()
    assert store.get_rom_transfer("old").status == "failed"
    assert store.get_rom_transfer("new").status == "pending"
