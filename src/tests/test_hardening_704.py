"""#704: blob store atomicity, presence monitor isolation, upload cap, pull-request validation."""
from __future__ import annotations

import hashlib
import os
import tarfile

import pytest

from server import api as api_module
from server.api import _core, blobs
from server.store import Store
from tests.conftest import AUTH


def _push(store, slug, data, tmp_path, name):
    src = store.new_upload_path()
    src.write_bytes(data)
    return store.push_save_file(slug, "dev", src, hashlib.sha256(data).hexdigest(), len(data))


def _game(store, slug="g"):
    store.ensure_device("dev", "dev")
    store.add_game(slug, slug, "GBA")


def test_failed_move_leaves_no_row(tmp_path, monkeypatch):
    store = Store(str(tmp_path))
    _game(store)
    src = store.new_upload_path()
    src.write_bytes(b"abc")

    def boom(*a, **k):
        raise OSError("disk")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        store.push_save_file("g", "dev", src, "h", 3)
    monkeypatch.undo()
    store._conn.commit()  # a later commit must not resurrect a row
    assert store.get_save_meta("g") is None


def test_pruned_files_removed_after_commit(tmp_path):
    store = Store(str(tmp_path))
    _game(store)
    for i in range(7):
        _push(store, "g", f"v{i}".encode(), tmp_path, i)
    assert len(store.list_save_history("g")) == 5
    assert len(list((store._blob_dir / "saves").iterdir())) == 5


def test_presence_tick_survives_bad_row(tmp_path, monkeypatch):
    store = Store(str(tmp_path))
    api_module.init(store, "")
    for d in ("bad", "good"):
        store.ensure_device(d, d)
    store._conn.execute("UPDATE devices SET last_seen_at = 'garbage' WHERE id = 'bad'")
    store._conn.execute("UPDATE devices SET last_seen_at = '2000-01-01T00:00:00' WHERE id = 'good'")  # naive
    store._conn.commit()
    with _core._presence_lock:
        _core._online_devices.update({"bad", "good"})
    _core._presence_tick()
    assert "good" not in _core._online_devices


@pytest.mark.asyncio
async def test_upload_over_cap_413_and_cleaned(make_client, monkeypatch):
    c = await make_client()
    await c.post("/games", json={"name": "Metroid", "console": "GBA"}, headers=AUTH)
    monkeypatch.setattr(blobs, "_MAX_UPLOAD_BYTES", 10)
    r = await c.post("/games/metroid/save", content=b"x" * 100, headers=AUTH)
    assert r.status_code == 413
    up = _core._get_store()._blob_dir / ".uploads"
    assert not up.exists() or list(up.iterdir()) == []


@pytest.mark.asyncio
async def test_failed_push_cleans_upload(make_client):
    c = await make_client()
    with pytest.raises(Exception):  # unknown slug: FK failure
        await c.post("/games/nope/save", content=b"x" * 20, headers=AUTH)
    up = _core._get_store()._blob_dir / ".uploads"
    assert not up.exists() or list(up.iterdir()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [[1], {"from_device_id": "x", "kind": "bogus"}])
async def test_pull_request_bad_body(client, body):
    await client.post("/games", json={"name": "Metroid", "console": "GBA"}, headers=AUTH)
    r = await client.post("/games/metroid/rom-pull-request", json=body, headers=AUTH)
    assert r.status_code == 400


def test_archive_memcard_folder_streams(tmp_path):
    store = Store(str(tmp_path))
    folder = tmp_path / "card"
    (folder / "sub").mkdir(parents=True)
    (folder / "sub" / "a.bin").write_bytes(b"data")
    path, h, size = store._archive_memcard_folder(folder)
    assert h == hashlib.sha256(path.read_bytes()).hexdigest()
    assert size == path.stat().st_size
    with tarfile.open(path, "r:gz") as tf:
        assert "sub/a.bin" in tf.getnames()
