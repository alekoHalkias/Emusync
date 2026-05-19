"""Tests for emusync.sync_client — SyncClient with mocked HTTP responses."""
import json

import httpx
import pytest

from emusync.sync_client import SyncClient


def make_client():
    return SyncClient(host="localhost", port=8765, token="test-token")


def mock_response(status_code=200, json_body=None, content=None, headers=None):
    """Build a minimal httpx.Response with a linked Request (required for raise_for_status)."""
    if json_body is not None:
        body = json.dumps(json_body).encode()
        h = {"content-type": "application/json"}
    else:
        body = content or b""
        h = {}
    if headers:
        h.update(headers)
    request = httpx.Request("GET", "http://localhost:8765/")
    response = httpx.Response(status_code, content=body, headers=h, request=request)
    return response


# ── health ─────────────────────────────────────────────────────────────────


class TestHealth:
    def test_health_returns_true_on_200(self, monkeypatch):
        monkeypatch.setattr(httpx, "get", lambda *a, **kw: mock_response(200))
        assert make_client().health() is True

    def test_health_returns_false_on_non_200(self, monkeypatch):
        monkeypatch.setattr(httpx, "get", lambda *a, **kw: mock_response(500))
        assert make_client().health() is False

    def test_health_returns_false_on_exception(self, monkeypatch):
        def raise_(*a, **kw):
            raise httpx.ConnectError("refused")

        monkeypatch.setattr(httpx, "get", raise_)
        assert make_client().health() is False


# ── pair ───────────────────────────────────────────────────────────────────


class TestPair:
    def test_pair_returns_token(self, monkeypatch):
        monkeypatch.setattr(
            httpx, "post", lambda *a, **kw: mock_response(200, json_body={"token": "new-tok"})
        )
        token = make_client().pair("master", "dev-1", "Desktop")
        assert token == "new-tok"

    def test_pair_raises_on_error(self, monkeypatch):
        monkeypatch.setattr(httpx, "post", lambda *a, **kw: mock_response(401))
        with pytest.raises(httpx.HTTPStatusError):
            make_client().pair("bad-token", "dev-1", "Desktop")


# ── pull_save ──────────────────────────────────────────────────────────────


class TestPullSave:
    def test_pull_save_writes_file(self, tmp_path, monkeypatch):
        save_data = b"save-bytes"
        monkeypatch.setattr(httpx, "get", lambda *a, **kw: mock_response(200, content=save_data))
        save_path = str(tmp_path / "game.sav")
        result = make_client().pull_save("zelda", save_path)
        assert result is True
        assert (tmp_path / "game.sav").read_bytes() == save_data

    def test_pull_save_returns_false_on_204(self, monkeypatch):
        monkeypatch.setattr(httpx, "get", lambda *a, **kw: mock_response(204))
        result = make_client().pull_save("zelda", "/tmp/game.sav")
        assert result is False

    def test_pull_save_creates_backup_if_file_exists(self, tmp_path, monkeypatch):
        save_path = tmp_path / "game.sav"
        save_path.write_bytes(b"old-save")
        monkeypatch.setattr(httpx, "get", lambda *a, **kw: mock_response(200, content=b"new-save"))
        make_client().pull_save("zelda", str(save_path))
        backup = tmp_path / "game.sav.bak"
        assert backup.exists()
        assert backup.read_bytes() == b"old-save"

    def test_pull_save_creates_parent_dirs(self, tmp_path, monkeypatch):
        monkeypatch.setattr(httpx, "get", lambda *a, **kw: mock_response(200, content=b"data"))
        deep = tmp_path / "a" / "b" / "game.sav"
        make_client().pull_save("zelda", str(deep))
        assert deep.exists()

    def test_pull_save_raises_on_error(self, monkeypatch):
        monkeypatch.setattr(httpx, "get", lambda *a, **kw: mock_response(500))
        with pytest.raises(httpx.HTTPStatusError):
            make_client().pull_save("zelda", "/tmp/game.sav")


# ── push_save ──────────────────────────────────────────────────────────────


class TestPushSave:
    def test_push_save_sends_file_content(self, tmp_path, monkeypatch):
        captured = {}

        def fake_post(url, content, headers, timeout):
            captured["content"] = content
            return mock_response(200, json_body={"sha256": "abc", "size": len(content)})

        monkeypatch.setattr(httpx, "post", fake_post)
        save_path = tmp_path / "game.sav"
        save_path.write_bytes(b"save-data")
        make_client().push_save("zelda", str(save_path))
        assert captured["content"] == b"save-data"

    def test_push_save_raises_on_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(httpx, "post", lambda *a, **kw: mock_response(500))
        save_path = tmp_path / "game.sav"
        save_path.write_bytes(b"data")
        with pytest.raises(httpx.HTTPStatusError):
            make_client().push_save("zelda", str(save_path))


# ── lock operations ────────────────────────────────────────────────────────


class TestLockOperations:
    def test_acquire_lock_success(self, monkeypatch):
        monkeypatch.setattr(
            httpx, "post", lambda *a, **kw: mock_response(200, json_body={"locked": True})
        )
        make_client().acquire_lock("zelda")  # should not raise

    def test_acquire_lock_raises_on_error(self, monkeypatch):
        monkeypatch.setattr(httpx, "post", lambda *a, **kw: mock_response(409))
        with pytest.raises(httpx.HTTPStatusError):
            make_client().acquire_lock("zelda")

    def test_release_lock_success(self, monkeypatch):
        monkeypatch.setattr(
            httpx, "delete", lambda *a, **kw: mock_response(200, json_body={"released": True})
        )
        make_client().release_lock("zelda")  # should not raise

    def test_release_lock_swallows_exception(self, monkeypatch):
        def raise_(*a, **kw):
            raise httpx.ConnectError("gone")

        monkeypatch.setattr(httpx, "delete", raise_)
        make_client().release_lock("zelda")  # should not raise


# ── game operations ────────────────────────────────────────────────────────


class TestGameOperations:
    def test_list_games(self, monkeypatch):
        games = [{"slug": "zelda", "name": "Zelda"}, {"slug": "mario", "name": "Mario"}]
        monkeypatch.setattr(httpx, "get", lambda *a, **kw: mock_response(200, json_body=games))
        result = make_client().list_games()
        assert len(result) == 2

    def test_add_game(self, monkeypatch):
        monkeypatch.setattr(
            httpx, "post", lambda *a, **kw: mock_response(201, json_body={"slug": "zelda"})
        )
        make_client().add_game("zelda", "Zelda")  # should not raise

    def test_remove_game(self, monkeypatch):
        monkeypatch.setattr(httpx, "delete", lambda *a, **kw: mock_response(204))
        make_client().remove_game("zelda")  # should not raise

    def test_get_game_returns_dict(self, monkeypatch):
        game = {"slug": "zelda", "name": "Zelda"}
        monkeypatch.setattr(httpx, "get", lambda *a, **kw: mock_response(200, json_body=game))
        result = make_client().get_game("zelda")
        assert result == game

    def test_get_game_returns_none_on_404(self, monkeypatch):
        monkeypatch.setattr(httpx, "get", lambda *a, **kw: mock_response(404))
        result = make_client().get_game("nonexistent")
        assert result is None

    def test_set_game_device(self, monkeypatch):
        monkeypatch.setattr(httpx, "put", lambda *a, **kw: mock_response(200, json_body={}))
        make_client().set_game_device("zelda", "/rom", "/save", "cmd")  # should not raise

    def test_get_game_device_returns_dict(self, monkeypatch):
        gd = {"rom_path": "/rom", "save_path": "/save"}
        monkeypatch.setattr(httpx, "get", lambda *a, **kw: mock_response(200, json_body=gd))
        result = make_client().get_game_device("zelda")
        assert result == gd

    def test_get_game_device_returns_none_on_404(self, monkeypatch):
        monkeypatch.setattr(httpx, "get", lambda *a, **kw: mock_response(404))
        result = make_client().get_game_device("zelda")
        assert result is None


# ── save meta / lock query ─────────────────────────────────────────────────


class TestMetaAndLockQuery:
    def test_get_save_meta_returns_dict(self, monkeypatch):
        meta = {"sha256": "abc", "size": 100}
        monkeypatch.setattr(httpx, "get", lambda *a, **kw: mock_response(200, json_body=meta))
        result = make_client().get_save_meta("zelda")
        assert result == meta

    def test_get_save_meta_returns_none_on_204(self, monkeypatch):
        monkeypatch.setattr(httpx, "get", lambda *a, **kw: mock_response(204))
        result = make_client().get_save_meta("zelda")
        assert result is None

    def test_get_lock(self, monkeypatch):
        lock = {"locked": True, "device_id": "dev-1"}
        monkeypatch.setattr(httpx, "get", lambda *a, **kw: mock_response(200, json_body=lock))
        result = make_client().get_lock("zelda")
        assert result == lock

    def test_list_devices(self, monkeypatch):
        devices = [{"id": "dev-1", "name": "Desktop"}]
        monkeypatch.setattr(httpx, "get", lambda *a, **kw: mock_response(200, json_body=devices))
        result = make_client().list_devices()
        assert result == devices
