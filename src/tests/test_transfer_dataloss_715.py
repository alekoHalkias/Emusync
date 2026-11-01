"""Failed, partial or empty transfers must not overwrite or hide data (#715)."""
from __future__ import annotations

import hashlib
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from server.api import _core, blobs
from server.sync_client import SyncClient
from tests.conftest import AUTH, _device_auth

GOOD = b"NEWROM" * 1000


class _Handler(BaseHTTPRequestHandler):
    mode = "ok"

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", str(len(GOOD)))
        if self.mode == "badhash":
            self.send_header("X-Rom-Hash", "0" * 64)
        self.end_headers()
        if self.mode == "truncate":
            self.wfile.write(GOOD[:100])
            self.wfile.flush()
            self.connection.close()
            return
        self.wfile.write(GOOD)

    def log_message(self, *a):
        pass


@pytest.fixture
def rom_client():
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    c = SyncClient("127.0.0.1", httpd.server_port, "", "dev", "dev")
    yield c, _Handler
    c.close()
    httpd.shutdown()


def _run(c, handler, mode, dest, expected=None):
    handler.mode = mode
    return c.download_transfer("t1", str(dest), expected_hash=expected)


@pytest.mark.parametrize("mode", ["badhash", "truncate"])
def test_failed_download_keeps_existing_rom(rom_client, tmp_path, mode):
    c, h = rom_client
    dest = tmp_path / "game.gba"
    dest.write_bytes(b"OLD")
    with pytest.raises(Exception):
        _run(c, h, mode, dest)
    assert dest.read_bytes() == b"OLD"
    assert list(tmp_path.iterdir()) == [dest]  # no .part left


def test_successful_download_replaces(rom_client, tmp_path):
    c, h = rom_client
    dest = tmp_path / "game.gba"
    dest.write_bytes(b"OLD")
    _run(c, h, "ok", dest, hashlib.sha256(GOOD).hexdigest())
    assert dest.read_bytes() == GOOD
    assert list(tmp_path.iterdir()) == [dest]


def test_extensionless_ok_directory_rejected(rom_client, tmp_path):
    c, h = rom_client
    _run(c, h, "ok", tmp_path / "NoExt")
    assert (tmp_path / "NoExt").read_bytes() == GOOD
    with pytest.raises(ValueError):
        _run(c, h, "ok", tmp_path)


@pytest.mark.asyncio
async def test_save_baseline_only_after_delivery(client):
    await client.post("/games", json={"name": "Zelda"}, headers=AUTH)
    await client.post("/games/zelda/save", content=b"SAVE", headers=AUTH)
    store = _core._get_store()
    resp = blobs._pull(blobs._SAVE, "zelda", "dev-b")
    assert store.get_save_sync_baseline("zelda", "dev-b") is None
    await resp.background()
    assert store.get_save_sync_baseline("zelda", "dev-b") is not None


@pytest.mark.asyncio
async def test_memcard_baseline_only_after_delivery(client):
    await client.post("/consoles/PS2/memcard", content=b"CARD", headers=AUTH)
    store = _core._get_store()
    resp = blobs.pull_console_memcard("PS2", "dev-b")
    assert store.get_console_save_sync_baseline("PS2", "dev-b") is None
    await resp.background()
    assert store.get_console_save_sync_baseline("PS2", "dev-b") is not None


@pytest.mark.asyncio
async def test_pull_without_save_records_no_baseline(client):
    await client.post("/games", json={"name": "Zelda"}, headers=AUTH)
    r = await client.get("/games/zelda/save", headers=_device_auth("dev-b", "B"))
    assert r.status_code == 204
    assert _core._get_store().get_save_sync_baseline("zelda", "dev-b") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/games/zelda/save", "/games/zelda/state", "/consoles/PS2/memcard"])
async def test_empty_upload_rejected(client, path):
    await client.post("/games", json={"name": "Zelda"}, headers=AUTH)
    r = await client.post(path, content=b"", headers=AUTH)
    assert r.status_code == 400
    assert (await client.get(path, headers=AUTH)).status_code == 204
    # a real upload afterwards still works
    assert (await client.post(path, content=b"DATA", headers=AUTH)).status_code == 200


def test_is_stale_handles_naive_and_garbage():
    assert _core._is_stale("2000-01-01T00:00:00") is True
    assert _core._is_stale("2999-01-01T00:00:00") is False
    assert _core._is_stale("not-a-date") is False
