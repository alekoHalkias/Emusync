"""Save push/pull, meta, two-device sync, and save history & rollback (#7)."""
from __future__ import annotations

import hashlib

import pytest

from tests.conftest import AUTH, _device_auth


# ── save push / pull ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_push_and_pull_save(client):
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=AUTH)

    save_v1 = b"\x00\x01\x02\x03" * 256
    r = await client.post("/games/pokemon-emerald/save", content=save_v1, headers=AUTH)
    assert r.status_code == 200
    pushed_hash = r.json()["hash"]
    assert pushed_hash == hashlib.sha256(save_v1).hexdigest()

    r = await client.get("/games/pokemon-emerald/save", headers=AUTH)
    assert r.status_code == 200
    assert r.content == save_v1
    assert r.headers["x-save-hash"] == pushed_hash


@pytest.mark.asyncio
async def test_push_save_updates_version(client):
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=AUTH)

    save_v1 = b"save version 1"
    save_v2 = b"save version 2 with more progress"

    await client.post("/games/pokemon-emerald/save", content=save_v1, headers=AUTH)
    await client.post("/games/pokemon-emerald/save", content=save_v2, headers=AUTH)

    r = await client.get("/games/pokemon-emerald/save", headers=AUTH)
    assert r.content == save_v2
    assert r.headers["x-save-hash"] == hashlib.sha256(save_v2).hexdigest()


@pytest.mark.asyncio
async def test_pull_save_no_save_returns_204(client):
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=AUTH)
    r = await client.get("/games/pokemon-emerald/save", headers=AUTH)
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_save_meta(client):
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=AUTH)

    save_data = b"some save data"
    await client.post("/games/pokemon-emerald/save", content=save_data, headers=AUTH)

    r = await client.get("/games/pokemon-emerald/save/meta", headers=AUTH)
    assert r.status_code == 200
    meta = r.json()
    assert meta["hash"] == hashlib.sha256(save_data).hexdigest()
    assert "pushed_at" in meta


@pytest.mark.asyncio
async def test_save_meta_returns_204_when_no_save(client):
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=AUTH)
    r = await client.get("/games/pokemon-emerald/save/meta", headers=AUTH)
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_push_save_twice_keeps_only_latest(client):
    """Pushing a save twice must replace the first — only one row in the DB."""
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=AUTH)

    await client.post("/games/pokemon-emerald/save", content=b"version one", headers=AUTH)
    await client.post("/games/pokemon-emerald/save", content=b"version two", headers=AUTH)

    r = await client.get("/games/pokemon-emerald/save", headers=AUTH)
    assert r.content == b"version two"


# ── two-device save sync ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_two_device_save_sync(client):
    """Device A pushes v1, device B pulls and verifies, B pushes v2, A pulls and gets v2."""
    auth_a = _device_auth("device-a", "Gaming PC")
    auth_b = _device_auth("device-b", "Steam Deck")

    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=auth_a)

    # Device A pushes v1
    save_v1 = b"save file version 1 - just started game"
    r = await client.post("/games/pokemon-emerald/save", content=save_v1, headers=auth_a)
    hash_v1 = r.json()["hash"]
    assert hash_v1 == hashlib.sha256(save_v1).hexdigest()

    # Device B pulls and verifies hash matches
    r = await client.get("/games/pokemon-emerald/save", headers=auth_b)
    assert r.status_code == 200
    assert r.content == save_v1
    assert r.headers["x-save-hash"] == hash_v1

    # Device B pushes v2
    save_v2 = b"save file version 2 - beat first gym"
    r = await client.post("/games/pokemon-emerald/save", content=save_v2, headers=auth_b)
    hash_v2 = r.json()["hash"]
    assert hash_v2 == hashlib.sha256(save_v2).hexdigest()
    assert hash_v2 != hash_v1

    # Device A pulls and gets v2
    r = await client.get("/games/pokemon-emerald/save", headers=auth_a)
    assert r.content == save_v2
    assert r.headers["x-save-hash"] == hash_v2


# ── save history & rollback (issue #7) ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_save_history_accumulates_generations(client):
    await client.post("/games", json={"name": "Zelda"}, headers=AUTH)
    for payload in (b"gen-one", b"gen-two-bigger", b"gen-three"):
        await client.post("/games/zelda/save", content=payload, headers=AUTH)

    r = await client.get("/games/zelda/save/history", headers=AUTH)
    assert r.status_code == 200
    history = r.json()
    assert len(history) == 3
    # Newest first; size reported.
    assert history[0]["hash"] == hashlib.sha256(b"gen-three").hexdigest()
    assert history[0]["size"] == len(b"gen-three")
    assert history[-1]["hash"] == hashlib.sha256(b"gen-one").hexdigest()


@pytest.mark.asyncio
async def test_save_history_dedupes_identical_pushes(client):
    await client.post("/games", json={"name": "Zelda"}, headers=AUTH)
    await client.post("/games/zelda/save", content=b"same", headers=AUTH)
    await client.post("/games/zelda/save", content=b"same", headers=AUTH)

    r = await client.get("/games/zelda/save/history", headers=AUTH)
    assert len(r.json()) == 1  # identical content does not create a new generation


@pytest.mark.asyncio
async def test_restore_save_makes_old_version_current(client):
    await client.post("/games", json={"name": "Zelda"}, headers=AUTH)
    await client.post("/games/zelda/save", content=b"good-save", headers=AUTH)
    await client.post("/games/zelda/save", content=b"bad-save", headers=AUTH)

    history = (await client.get("/games/zelda/save/history", headers=AUTH)).json()
    good_version = next(v for v in history if v["hash"] == hashlib.sha256(b"good-save").hexdigest())

    r = await client.post("/games/zelda/save/restore", json={"version_id": good_version["id"]}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["hash"] == hashlib.sha256(b"good-save").hexdigest()

    # Pulling now returns the restored content.
    pulled = await client.get("/games/zelda/save", headers=AUTH)
    assert pulled.content == b"good-save"
    # Restore added a forward generation rather than dropping anything.
    assert len(history) == 2


@pytest.mark.asyncio
async def test_restore_unknown_version_returns_404(client):
    await client.post("/games", json={"name": "Zelda"}, headers=AUTH)
    await client.post("/games/zelda/save", content=b"x", headers=AUTH)
    r = await client.post("/games/zelda/save/restore", json={"version_id": "no-such-id"}, headers=AUTH)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_save_history_pruned_to_limit(client):
    from server.store.blobs import HISTORY_LIMIT
    await client.post("/games", json={"name": "Zelda"}, headers=AUTH)
    for i in range(HISTORY_LIMIT + 5):
        await client.post("/games/zelda/save", content=f"gen-{i}".encode(), headers=AUTH)
    history = (await client.get("/games/zelda/save/history", headers=AUTH)).json()
    assert len(history) == HISTORY_LIMIT
    assert history[0]["hash"] == hashlib.sha256(f"gen-{HISTORY_LIMIT + 4}".encode()).hexdigest()


@pytest.mark.asyncio
async def test_save_history_404_for_unknown_game(client):
    r = await client.get("/games/ghost/save/history", headers=AUTH)
    assert r.status_code == 404
