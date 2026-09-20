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


# ── shared-card history & rollback (issue #480) ─────────────────────────────────

def test_console_save_history_accumulates_generations():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(tmp)
        for payload in (b"gen-one", b"gen-two-bigger", b"gen-three"):
            up = store.new_upload_path()
            up.write_bytes(payload)
            store.push_console_save_file("PS2", "dev-1", up, hashlib.sha256(payload).hexdigest(), len(payload))

        history = store.list_console_save_history("PS2")
        assert len(history) == 3
        assert history[0]["hash"] == hashlib.sha256(b"gen-three").hexdigest()
        assert history[-1]["hash"] == hashlib.sha256(b"gen-one").hexdigest()


def test_console_save_history_dedupes_identical_pushes():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(tmp)
        for _ in range(2):
            up = store.new_upload_path()
            up.write_bytes(b"same")
            store.push_console_save_file("PS2", "dev-1", up, hashlib.sha256(b"same").hexdigest(), 4)
        assert len(store.list_console_save_history("PS2")) == 1


def test_console_save_history_pruned_to_limit():
    from server.store.blobs import HISTORY_LIMIT
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(tmp)
        for i in range(HISTORY_LIMIT + 5):
            payload = f"gen-{i}".encode()
            up = store.new_upload_path()
            up.write_bytes(payload)
            store.push_console_save_file("PS2", "dev-1", up, hashlib.sha256(payload).hexdigest(), len(payload))
        history = store.list_console_save_history("PS2")
        assert len(history) == HISTORY_LIMIT
        assert history[0]["hash"] == hashlib.sha256(f"gen-{HISTORY_LIMIT + 4}".encode()).hexdigest()


def test_restore_console_save_makes_old_version_current():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(tmp)
        for payload in (b"good-card", b"bad-card"):
            up = store.new_upload_path()
            up.write_bytes(payload)
            store.push_console_save_file("PS2", "dev-1", up, hashlib.sha256(payload).hexdigest(), len(payload))

        history = store.list_console_save_history("PS2")
        good_version = next(v for v in history if v["hash"] == hashlib.sha256(b"good-card").hexdigest())

        meta = store.restore_console_save("PS2", good_version["id"])
        assert meta["hash"] == hashlib.sha256(b"good-card").hexdigest()

        path, _ = store.pull_console_save_path("PS2")
        assert path.read_bytes() == b"good-card"
        # Restore added a forward generation rather than dropping anything.
        assert len(store.list_console_save_history("PS2")) == 3


def test_restore_console_save_carries_card_format_forward():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(tmp)
        up = store.new_upload_path()
        up.write_bytes(b"gc card v1")
        store.push_console_save_file("GC", "dev-1", up, hashlib.sha256(b"gc card v1").hexdigest(), 10,
                                      card_format="GCIFolder")
        up2 = store.new_upload_path()
        up2.write_bytes(b"gc card v2")
        store.push_console_save_file("GC", "dev-1", up2, hashlib.sha256(b"gc card v2").hexdigest(), 10,
                                      card_format="GCIFolder")

        old_version = store.list_console_save_history("GC")[-1]
        meta = store.restore_console_save("GC", old_version["id"])
        assert meta["card_format"] == "GCIFolder"
        assert store.get_console_save_meta("GC")["card_format"] == "GCIFolder"


def test_restore_console_save_unknown_version_returns_none():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(tmp)
        assert store.restore_console_save("PS2", "no-such-id") is None


@pytest.mark.asyncio
async def test_memcard_history_route_accumulates_and_restores(client):
    await client.post("/consoles/PS2/memcard", content=b"good-card", headers=AUTH)
    await client.post("/consoles/PS2/memcard", content=b"bad-card", headers=AUTH)

    r = await client.get("/consoles/PS2/memcard/history", headers=AUTH)
    assert r.status_code == 200
    history = r.json()
    assert len(history) == 2
    good_version = next(v for v in history if v["hash"] == hashlib.sha256(b"good-card").hexdigest())

    r = await client.post("/consoles/PS2/memcard/restore", json={"version_id": good_version["id"]}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["hash"] == hashlib.sha256(b"good-card").hexdigest()

    pulled = await client.get("/consoles/PS2/memcard", headers=AUTH)
    assert pulled.content == b"good-card"


@pytest.mark.asyncio
async def test_memcard_restore_unknown_version_returns_404(client):
    await client.post("/consoles/PS2/memcard", content=b"x", headers=AUTH)
    r = await client.post("/consoles/PS2/memcard/restore", json={"version_id": "no-such-id"}, headers=AUTH)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_memcard_history_empty_for_unknown_console(client):
    r = await client.get("/consoles/GHOST/memcard/history", headers=AUTH)
    assert r.status_code == 200
    assert r.json() == []


# ── shared-card sync baseline (issue #481) ──────────────────────────────────────

def test_console_save_sync_baseline_round_trips():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(tmp)
        assert store.get_console_save_sync_baseline("PS2", "dev-1") is None
        store.set_console_save_sync_baseline("PS2", "dev-1", "abc123", "2026-01-01T00:00:00+00:00")
        baseline = store.get_console_save_sync_baseline("PS2", "dev-1")
        assert baseline["hash"] == "abc123"
        assert baseline["synced_at"] == "2026-01-01T00:00:00+00:00"
        # A different device has no baseline of its own.
        assert store.get_console_save_sync_baseline("PS2", "dev-2") is None


@pytest.mark.asyncio
async def test_memcard_sync_baseline_missing_returns_204(client):
    r = await client.get("/consoles/PS2/memcard/sync-baseline", headers=AUTH)
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_memcard_push_records_pushing_devices_own_baseline(client):
    data = b"pushed card bytes"
    r = await client.post("/consoles/PS2/memcard", content=data, headers=AUTH)
    pushed_hash = r.json()["hash"]

    baseline = (await client.get("/consoles/PS2/memcard/sync-baseline", headers=AUTH)).json()
    assert baseline["hash"] == pushed_hash == hashlib.sha256(data).hexdigest()


@pytest.mark.asyncio
async def test_memcard_pull_records_pulling_devices_own_baseline(client):
    auth_a = _device_auth("device-a", "Gaming PC")
    auth_b = _device_auth("device-b", "Steam Deck")
    data = b"pushed by A"
    r = await client.post("/consoles/PS2/memcard", content=data, headers=auth_a)
    pushed_hash = r.json()["hash"]

    # B hasn't pulled yet — no baseline of its own, even though A has one.
    assert (await client.get("/consoles/PS2/memcard/sync-baseline", headers=auth_b)).status_code == 204

    await client.get("/consoles/PS2/memcard", headers=auth_b)
    baseline_b = (await client.get("/consoles/PS2/memcard/sync-baseline", headers=auth_b)).json()
    assert baseline_b["hash"] == pushed_hash


def test_memcard_client_get_save_sync_baseline_delegates_to_console_scoped_endpoint():
    """_MemcardClient (cli/run_ps2.py) used to hardcode None here — confirm it
    now actually reads the console-scoped baseline instead (#481)."""
    class _FakeSyncClient:
        def __init__(self):
            self.requested_key = None

        def get_console_save_sync_baseline(self, console_key):
            self.requested_key = console_key
            return {"hash": "the-baseline-hash", "synced_at": "2026-01-01T00:00:00+00:00"}

    from cli.run_ps2 import _MemcardClient

    fake = _FakeSyncClient()
    mc = _MemcardClient(fake, "PS2", cfg=None)
    baseline = mc.get_save_sync_baseline("PS2")  # arg is ignored, self._key is used

    assert fake.requested_key == "PS2"
    assert baseline["hash"] == "the-baseline-hash"
