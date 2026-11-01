"""Regression tests for #691: transfer filename traversal, unsafe tar extraction,
presence monitor NameError."""
from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from server import api as api_module
from server.api import _core
from server.store import Store
from tests.conftest import MASTER_PIN, _device_auth


# ── rom transfer filename ─────────────────────────────────────────────────────

async def _push_named(c, filename):
    auth_src = _device_auth("dev-src", "PC")
    await c.get("/games", headers=auth_src)
    await c.get("/games", headers=_device_auth("dev-dst", "Deck"))
    await c.post("/games", json={"name": "Metroid", "console": "GBA"}, headers=auth_src)
    return await c.post(
        "/games/metroid/rom-transfer", content=b"DATA",
        headers={**auth_src, "X-To-Device-ID": "dev-dst", "X-Filename": filename},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("name,expected", [
    ("../../x", "x"), ("/etc/passwd", "passwd"), ("..\\..\\y", "y"),
])
async def test_rom_transfer_filename_confined_to_staging(make_client, tmp_path, name, expected):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    c = await make_client(data_dir=str(data_dir))
    r = await _push_named(c, name)
    assert r.status_code == 200
    found = [p for p in tmp_path.rglob(expected) if p.is_file()]
    assert len(found) == 1
    assert found[0].parent.parent == data_dir / "rom_staging"


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["..", "/", "."])
async def test_rom_transfer_rejects_bad_filename(make_client, tmp_path, name):
    c = await make_client(data_dir=str(tmp_path))
    r = await _push_named(c, name)
    assert r.status_code == 400
    staging = tmp_path / "rom_staging"
    assert not staging.exists() or not list(staging.iterdir())


# ── presence monitor ──────────────────────────────────────────────────────────

def test_monitor_lockless_offline_device_does_not_abort_pass(capsys):
    """Offline device with no locks must not NameError; the next device's locks
    are still released and each released lock is logged."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        api_module.init(store, MASTER_PIN)
        old = (datetime.now(timezone.utc) - timedelta(
            seconds=_core.OFFLINE_TIMEOUT_SECONDS + 60)).isoformat()
        store.add_game("g1", "Game One", "GBA")
        store.add_game("g2", "Game Two", "GBA")
        for dev in ("a-nolocks", "b-locks"):
            store.ensure_device(dev, dev)
            store._conn.execute(
                "UPDATE devices SET last_ip=?, last_seen_at=? WHERE id=?",
                ("127.0.0.1", old, dev))
        store._conn.commit()
        store.acquire_lock("g1", "b-locks")
        store.acquire_lock("g2", "b-locks")
        with _core._presence_lock:
            _core._online_devices.update({"a-nolocks", "b-locks"})
            _core._device_names.update({"a-nolocks": "A", "b-locks": "B"})

        ticks = iter((0,))

        def one_shot_sleep(_s):
            try:
                next(ticks)
            except StopIteration:
                raise KeyboardInterrupt

        with patch("time.sleep", one_shot_sleep):
            try:
                _core._monitor_presence()
            except KeyboardInterrupt:
                pass

        assert store.get_lock("g1") is None and store.get_lock("g2") is None
        assert capsys.readouterr().out.count("lock released") == 2
