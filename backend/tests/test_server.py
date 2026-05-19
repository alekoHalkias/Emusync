"""Tests for emusync.server — all HTTP endpoints via FastAPI TestClient."""
import uuid

import pytest
from fastapi.testclient import TestClient

from emusync.server import create_app
from emusync.store import Store


@pytest.fixture
def db(tmp_path):
    return Store(str(tmp_path / "data"))


@pytest.fixture
def master_token():
    return str(uuid.uuid4())


@pytest.fixture
def client(db, master_token):
    app = create_app(db, master_token)
    return TestClient(app)


@pytest.fixture
def device_token(client, master_token):
    """Pair a device and return its auth token."""
    device_id = str(uuid.uuid4())
    r = client.post(
        "/pair",
        json={"master_token": master_token, "device_id": device_id, "device_name": "TestDevice"},
    )
    assert r.status_code == 200
    return r.json()["token"], device_id


@pytest.fixture
def auth_headers(device_token):
    token, _ = device_token
    return {"Authorization": f"Bearer {token}"}


# ── Health ─────────────────────────────────────────────────────────────────


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ── Pairing ────────────────────────────────────────────────────────────────


class TestPairing:
    def test_pair_success(self, client, master_token):
        device_id = str(uuid.uuid4())
        r = client.post(
            "/pair",
            json={"master_token": master_token, "device_id": device_id, "device_name": "Dev"},
        )
        assert r.status_code == 200
        body = r.json()
        assert "token" in body
        assert body["device_id"] == device_id

    def test_pair_wrong_token(self, client):
        r = client.post(
            "/pair",
            json={"master_token": "wrong", "device_id": "x", "device_name": "Dev"},
        )
        assert r.status_code == 401

    def test_pair_returns_unique_tokens(self, client, master_token):
        def pair():
            r = client.post(
                "/pair",
                json={
                    "master_token": master_token,
                    "device_id": str(uuid.uuid4()),
                    "device_name": "Dev",
                },
            )
            return r.json()["token"]

        t1, t2 = pair(), pair()
        assert t1 != t2


# ── Auth guard ─────────────────────────────────────────────────────────────


class TestAuthGuard:
    def test_missing_token_returns_401(self, client):
        r = client.get("/games")
        assert r.status_code == 401

    def test_invalid_token_returns_401(self, client):
        r = client.get("/games", headers={"Authorization": "Bearer bad-token"})
        assert r.status_code == 401


# ── Devices ────────────────────────────────────────────────────────────────


class TestDevicesEndpoint:
    def test_list_devices(self, client, auth_headers, device_token):
        _, device_id = device_token
        r = client.get("/devices", headers=auth_headers)
        assert r.status_code == 200
        ids = [d["id"] for d in r.json()]
        assert device_id in ids


# ── Games CRUD ─────────────────────────────────────────────────────────────


class TestGamesCRUD:
    def test_add_game(self, client, auth_headers):
        r = client.post("/games", json={"slug": "zelda", "name": "Zelda"}, headers=auth_headers)
        assert r.status_code == 201
        assert r.json()["slug"] == "zelda"

    def test_list_games_empty(self, client, auth_headers):
        r = client.get("/games", headers=auth_headers)
        assert r.status_code == 200
        assert r.json() == []

    def test_list_games_returns_added(self, client, auth_headers):
        client.post("/games", json={"slug": "zelda", "name": "Zelda"}, headers=auth_headers)
        client.post("/games", json={"slug": "mario", "name": "Mario"}, headers=auth_headers)
        r = client.get("/games", headers=auth_headers)
        slugs = [g["slug"] for g in r.json()]
        assert "zelda" in slugs
        assert "mario" in slugs

    def test_get_game(self, client, auth_headers):
        client.post("/games", json={"slug": "zelda", "name": "Zelda"}, headers=auth_headers)
        r = client.get("/games/zelda", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["name"] == "Zelda"

    def test_get_game_not_found(self, client, auth_headers):
        r = client.get("/games/nonexistent", headers=auth_headers)
        assert r.status_code == 404

    def test_update_game_name(self, client, auth_headers):
        client.post("/games", json={"slug": "zelda", "name": "Old"}, headers=auth_headers)
        r = client.put("/games/zelda", json={"name": "New"}, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["name"] == "New"

    def test_update_game_not_found(self, client, auth_headers):
        r = client.put("/games/nonexistent", json={"name": "X"}, headers=auth_headers)
        assert r.status_code == 404

    def test_remove_game(self, client, auth_headers):
        client.post("/games", json={"slug": "zelda", "name": "Zelda"}, headers=auth_headers)
        r = client.delete("/games/zelda", headers=auth_headers)
        assert r.status_code == 204
        r = client.get("/games/zelda", headers=auth_headers)
        assert r.status_code == 404

    def test_remove_game_not_found(self, client, auth_headers):
        r = client.delete("/games/nonexistent", headers=auth_headers)
        assert r.status_code == 404


# ── Game-device config ─────────────────────────────────────────────────────


class TestGameDeviceEndpoints:
    def test_set_and_get_game_device(self, client, auth_headers):
        client.post("/games", json={"slug": "zelda", "name": "Zelda"}, headers=auth_headers)
        r = client.put(
            "/games/zelda/device",
            json={"rom_path": "/rom", "save_path": "/save", "launch_command": "cmd"},
            headers=auth_headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["rom_path"] == "/rom"
        assert body["save_path"] == "/save"

    def test_get_game_device_not_configured(self, client, auth_headers):
        r = client.get("/games/zelda/device", headers=auth_headers)
        assert r.status_code == 404

    def test_set_game_device_partial_update(self, client, auth_headers):
        client.post("/games", json={"slug": "zelda", "name": "Zelda"}, headers=auth_headers)
        client.put(
            "/games/zelda/device",
            json={"rom_path": "/rom", "save_path": "/save", "launch_command": "cmd1"},
            headers=auth_headers,
        )
        r = client.put(
            "/games/zelda/device",
            json={"rom_path": "/new-rom", "save_path": "/save", "launch_command": "cmd1"},
            headers=auth_headers,
        )
        assert r.json()["rom_path"] == "/new-rom"


# ── Saves ──────────────────────────────────────────────────────────────────


class TestSaveEndpoints:
    def test_push_and_pull_save(self, client, auth_headers):
        save_data = b"my-save-bytes"
        r = client.post(
            "/games/zelda/save",
            content=save_data,
            headers={**auth_headers, "Content-Type": "application/octet-stream"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["size"] == len(save_data)

        r = client.get("/games/zelda/save", headers=auth_headers)
        assert r.status_code == 200
        assert r.content == save_data

    def test_pull_save_no_data_returns_204(self, client, auth_headers):
        r = client.get("/games/zelda/save", headers=auth_headers)
        assert r.status_code == 204

    def test_push_save_empty_body_returns_400(self, client, auth_headers):
        r = client.post(
            "/games/zelda/save",
            content=b"",
            headers={**auth_headers, "Content-Type": "application/octet-stream"},
        )
        assert r.status_code == 400

    def test_get_save_meta(self, client, auth_headers):
        save_data = b"meta-test"
        client.post(
            "/games/zelda/save",
            content=save_data,
            headers={**auth_headers, "Content-Type": "application/octet-stream"},
        )
        r = client.get("/games/zelda/save/meta", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["size"] == len(save_data)
        assert len(body["sha256"]) == 64

    def test_get_save_meta_no_data_returns_204(self, client, auth_headers):
        r = client.get("/games/zelda/save/meta", headers=auth_headers)
        assert r.status_code == 204

    def test_pull_save_response_headers(self, client, auth_headers):
        save_data = b"header-test"
        client.post(
            "/games/zelda/save",
            content=save_data,
            headers={**auth_headers, "Content-Type": "application/octet-stream"},
        )
        r = client.get("/games/zelda/save", headers=auth_headers)
        assert "x-save-sha256" in r.headers
        assert r.headers["x-save-size"] == str(len(save_data))


# ── Locks ──────────────────────────────────────────────────────────────────


class TestLockEndpoints:
    def test_acquire_and_get_lock(self, client, auth_headers):
        r = client.post("/games/zelda/lock", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["locked"] is True

        r = client.get("/games/zelda/lock", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["locked"] is True

    def test_get_lock_when_unlocked(self, client, auth_headers):
        r = client.get("/games/zelda/lock", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["locked"] is False

    def test_release_lock(self, client, auth_headers):
        client.post("/games/zelda/lock", headers=auth_headers)
        r = client.delete("/games/zelda/lock", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["released"] is True
        r = client.get("/games/zelda/lock", headers=auth_headers)
        assert r.json()["locked"] is False

    def test_lock_conflict_returns_409(self, client, master_token, db):
        # Pair a second device
        r = client.post(
            "/pair",
            json={"master_token": master_token, "device_id": "dev-2", "device_name": "Dev2"},
        )
        token2 = r.json()["token"]
        headers2 = {"Authorization": f"Bearer {token2}"}

        # First device acquires lock
        client.post("/games/zelda/lock", headers={"Authorization": f"Bearer {client.headers.get('Authorization', '')}"})
        # Use db directly to acquire the lock for dev-1
        db.acquire_lock("zelda", "dev-1-direct")

        # Second device tries to acquire
        # First acquire with auth_headers fixture device
        token1, dev_id1 = (
            client.post(
                "/pair",
                json={"master_token": master_token, "device_id": "dev-1-direct", "device_name": "Dev1"},
            ).json()["token"],
            "dev-1-direct",
        )
        headers1 = {"Authorization": f"Bearer {token1}"}
        # Acquire lock with dev-1
        client.post("/games/zelda/lock", headers=headers1)
        # dev-2 tries — should get 409
        r = client.post("/games/zelda/lock", headers=headers2)
        assert r.status_code == 409

    def test_lock_info_includes_device_id(self, client, auth_headers, device_token):
        _, device_id = device_token
        client.post("/games/zelda/lock", headers=auth_headers)
        r = client.get("/games/zelda/lock", headers=auth_headers)
        body = r.json()
        assert body["device_id"] == device_id
