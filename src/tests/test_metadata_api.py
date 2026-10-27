"""Game metadata cache + manual override (issue #578). Real SQLite and a real
local HTTP stub standing in for Wikipedia (no mocks)."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from server import config
from server.api import metadata as md
from server.store import Store
from tests.conftest import AUTH

HITS: list[str] = []


class _Wiki(BaseHTTPRequestHandler):
    def do_GET(self):
        HITS.append(self.path)
        if "/search/title" in self.path:
            body = {"pages": [{"key": "Test_Game"}]}
        else:
            body = {"extract": "A fine game.", "thumbnail": {"source": "http://img/c.png"}}
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


@pytest.fixture
def wiki(monkeypatch, tmp_path):
    HITS.clear()
    srv = HTTPServer(("127.0.0.1", 0), _Wiki)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(md, "WIKI_BASE", f"http://127.0.0.1:{srv.server_port}")
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "emusync.toml")
    yield
    srv.shutdown()


def _toggle(on: bool):
    cfg = config.load()
    cfg.auto_fetch_metadata = on
    config.save(cfg)


async def _game(client):
    r = await client.post("/games", json={"name": "Test Game"}, headers=AUTH)
    return r.json()["slug"]


@pytest.mark.asyncio
async def test_unknown_game_404(client, wiki):
    r = await client.get("/games/nope/metadata", headers=AUTH)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_autofetch_caches(client, wiki):
    slug = await _game(client)
    r = await client.get(f"/games/{slug}/metadata", headers=AUTH)
    assert r.json()["synopsis"] == "A fine game." and r.json()["source"] == "wikipedia"
    n = len(HITS)
    await client.get(f"/games/{slug}/metadata", headers=AUTH)
    assert len(HITS) == n  # served from cache


@pytest.mark.asyncio
async def test_toggle_off_skips_fetch(client, wiki):
    _toggle(False)
    slug = await _game(client)
    r = await client.get(f"/games/{slug}/metadata", headers=AUTH)
    assert r.json()["synopsis"] == "" and not HITS


@pytest.mark.asyncio
async def test_manual_survives_autofetch_and_delete_clears(client, wiki):
    slug = await _game(client)
    r = await client.put(f"/games/{slug}/metadata", json={"synopsis": "mine"}, headers=AUTH)
    assert r.json()["source"] == "manual"
    r = await client.get(f"/games/{slug}/metadata", headers=AUTH)
    assert r.json()["synopsis"] == "mine" and not HITS
    await client.delete(f"/games/{slug}/metadata", headers=AUTH)
    r = await client.get(f"/games/{slug}/metadata", headers=AUTH)
    assert r.json()["source"] == "wikipedia"


@pytest.mark.asyncio
async def test_offline_returns_empty(client, wiki, monkeypatch):
    monkeypatch.setattr(md, "WIKI_BASE", "http://127.0.0.1:1")
    slug = await _game(client)
    r = await client.get(f"/games/{slug}/metadata", headers=AUTH)
    assert r.status_code == 200 and r.json()["synopsis"] == ""


@pytest.mark.asyncio
async def test_stale_auto_row_refetched(client, wiki):
    slug = await _game(client)
    await client.get(f"/games/{slug}/metadata", headers=AUTH)
    store = md._get_store()
    store._conn.execute("UPDATE game_metadata SET fetched_at='2000-01-01T00:00:00+00:00'")
    store._conn.commit()
    n = len(HITS)
    await client.get(f"/games/{slug}/metadata", headers=AUTH)
    assert len(HITS) > n


def test_store_refuses_overwrite_of_manual(tmp_path):
    s = Store(str(tmp_path))
    s.add_game("a", "A")
    assert s.set_metadata("a", {"synopsis": "m"}, "manual")
    assert not s.set_metadata("a", {"synopsis": "w"}, "wikipedia")
    assert s.get_metadata("a")["synopsis"] == "m"


def test_migration_from_v27_creates_table(tmp_path):
    s = Store(str(tmp_path / "fresh"))
    s._conn.execute("DROP TABLE game_metadata")
    s._conn.execute("PRAGMA user_version = 27")
    s._conn.commit()
    s2 = Store(str(tmp_path / "fresh"))
    assert s2._conn.execute("SELECT count(*) FROM game_metadata").fetchone()[0] == 0


def test_config_toggle_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "emusync.toml")
    _toggle(False)
    assert config.load().auto_fetch_metadata is False
