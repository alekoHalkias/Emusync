"""Console-scoped shared memory card (PS2) — issue #295.

One card per console_key, shared across every game on the console and every
device, single generation (newest-wins overwrite).
"""
from __future__ import annotations

import hashlib
import tempfile

import pytest

from server.store import Store
from tests.conftest import AUTH, _device_auth


# ── store level ──────────────────────────────────────────────────────────────────

def test_console_save_push_pull_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(tmp)
        upload = store.new_upload_path()
        data = b"PS2 memory card v1" * 100
        upload.write_bytes(data)
        h = hashlib.sha256(data).hexdigest()
        meta = store.push_console_save_file("PS2", "dev-1", upload, h, len(data))
        assert meta["hash"] == h and meta["size"] == len(data)

        path, pulled_meta = store.pull_console_save_path("PS2")
        assert path is not None and path.read_bytes() == data
        assert pulled_meta["hash"] == h
        assert store.get_console_save_meta("PS2")["device_id"] == "dev-1"


def test_console_save_overwrite_is_newest_wins():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(tmp)
        for payload, dev in ((b"card-one", "dev-1"), (b"card-two-bigger", "dev-2")):
            up = store.new_upload_path()
            up.write_bytes(payload)
            store.push_console_save_file("PS2", dev, up, hashlib.sha256(payload).hexdigest(), len(payload))
        path, meta = store.pull_console_save_path("PS2")
        assert path.read_bytes() == b"card-two-bigger"
        assert meta["device_id"] == "dev-2"  # last writer wins


def test_console_save_missing_returns_none():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(tmp)
        assert store.get_console_save_meta("PS2") is None
        assert store.pull_console_save_path("PS2") == (None, None)


def test_console_save_card_format_round_trips(tmp_path):
    """card_format (#428) travels through push/pull/meta unchanged, and
    defaults to '' for consoles/pushes that don't set it."""
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(tmp)
        upload = store.new_upload_path()
        data = b"gc card"
        upload.write_bytes(data)
        h = hashlib.sha256(data).hexdigest()
        meta = store.push_console_save_file("GC", "dev-1", upload, h, len(data), card_format="GCIFolder")
        assert meta["card_format"] == "GCIFolder"
        assert store.get_console_save_meta("GC")["card_format"] == "GCIFolder"
        path, pulled_meta = store.pull_console_save_path("GC")
        assert pulled_meta["card_format"] == "GCIFolder"

        upload2 = store.new_upload_path()
        upload2.write_bytes(b"ps2 card")
        store.push_console_save_file("PS2", "dev-1", upload2, "h2", 8)
        assert store.get_console_save_meta("PS2")["card_format"] == ""


# ── API level ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_memcard_push_and_pull(client):
    card = b"\x01\x02\x03\x04" * 512
    r = await client.post("/consoles/PS2/memcard", content=card, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["hash"] == hashlib.sha256(card).hexdigest()

    r = await client.get("/consoles/PS2/memcard", headers=AUTH)
    assert r.status_code == 200
    assert r.content == card
    assert r.headers["x-save-hash"] == hashlib.sha256(card).hexdigest()


@pytest.mark.asyncio
async def test_memcard_pull_204_when_absent(client):
    r = await client.get("/consoles/PS2/memcard", headers=AUTH)
    assert r.status_code == 204
    r = await client.get("/consoles/PS2/memcard/meta", headers=AUTH)
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_memcard_meta_after_push(client):
    card = b"some memory card bytes"
    await client.post("/consoles/PS2/memcard", content=card, headers=AUTH)
    r = await client.get("/consoles/PS2/memcard/meta", headers=AUTH)
    assert r.status_code == 200
    meta = r.json()
    assert meta["hash"] == hashlib.sha256(card).hexdigest()
    assert meta["size"] == len(card)


@pytest.mark.asyncio
async def test_memcard_is_shared_across_devices(client):
    """The card is keyed by console, so device B sees what device A pushed —
    this is the whole point of a console-scoped shared save (issue #295)."""
    auth_a = _device_auth("dev-a", "PC")
    auth_b = _device_auth("dev-b", "Steam Deck")
    card = b"shared across the whole PS2 console"
    await client.post("/consoles/PS2/memcard", content=card, headers=auth_a)

    r = await client.get("/consoles/PS2/memcard", headers=auth_b)
    assert r.status_code == 200
    assert r.content == card


@pytest.mark.asyncio
async def test_memcard_requires_auth(client):
    r = await client.get("/consoles/PS2/memcard")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_memcard_card_format_header_round_trips(client):
    """X-Card-Format (#428) propagates push -> pull and push -> meta, so a
    pulling device can compare its own Dolphin setting against it."""
    card = b"gc card bytes"
    headers = dict(AUTH, **{"X-Card-Format": "GCIFolder"})
    r = await client.post("/consoles/GC/memcard", content=card, headers=headers)
    assert r.status_code == 200

    r = await client.get("/consoles/GC/memcard", headers=AUTH)
    assert r.headers["x-card-format"] == "GCIFolder"

    r = await client.get("/consoles/GC/memcard/meta", headers=AUTH)
    assert r.json()["card_format"] == "GCIFolder"


@pytest.mark.asyncio
async def test_memcard_card_format_defaults_empty_when_not_sent(client):
    card = b"ps2 card bytes"
    await client.post("/consoles/PS2/memcard", content=card, headers=AUTH)
    r = await client.get("/consoles/PS2/memcard/meta", headers=AUTH)
    assert r.json()["card_format"] == ""
