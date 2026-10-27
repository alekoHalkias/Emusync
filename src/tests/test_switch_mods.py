"""Communal Switch mod pool tests (issue #444): store, API, and the
name-only local↔pool sync logic in cli/run_switch.py.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from cli.run_switch import _local_switch_mods, _switch_load_root_for, _sync_switch_mods
from server.store import Store
from server.sync_client import SyncClient
from tests.conftest import AUTH


# ── store ────────────────────────────────────────────────────────────────────

def test_add_and_list_switch_mod():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        store.ensure_device("dev-1", "PC")
        src = Path(tmpdir) / "staged.tar"
        src.write_bytes(b"mod bytes")

        added = store.add_switch_mod("0100000011D90000", "Cool Mod", "dev-1", src, 9)

        assert added is True
        mods = store.list_switch_mods("0100000011D90000")
        assert len(mods) == 1
        assert mods[0]["mod_name"] == "Cool Mod"
        assert mods[0]["size"] == 9
        assert mods[0]["pushed_by"] == "dev-1"
        path = store.get_switch_mod_path("0100000011D90000", "Cool Mod")
        assert path is not None and path.read_bytes() == b"mod bytes"


def test_add_switch_mod_is_purely_additive():
    """A second push of a mod that already exists by name is a no-op — the
    pool never overwrites, matching the "purely additive" design (#444)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        store.ensure_device("dev-1", "PC")
        store.ensure_device("dev-2", "Deck")
        src1 = Path(tmpdir) / "first.tar"
        src1.write_bytes(b"original")
        store.add_switch_mod("0100000011D90000", "Cool Mod", "dev-1", src1, 8)

        src2 = Path(tmpdir) / "second.tar"
        src2.write_bytes(b"different bytes pushed later")
        added = store.add_switch_mod("0100000011D90000", "Cool Mod", "dev-2", src2, 29)

        assert added is False
        assert not src2.exists()  # discarded, not left behind
        mods = store.list_switch_mods("0100000011D90000")
        assert len(mods) == 1
        assert mods[0]["pushed_by"] == "dev-1"  # original push wins
        path = store.get_switch_mod_path("0100000011D90000", "Cool Mod")
        assert path.read_bytes() == b"original"


def test_get_switch_mod_path_none_when_absent():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        assert store.get_switch_mod_path("deadbeef00000000", "Nope") is None


def test_list_switch_mods_scoped_by_title_id():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        store.ensure_device("dev-1", "PC")
        src_a = Path(tmpdir) / "a.tar"
        src_a.write_bytes(b"a")
        src_b = Path(tmpdir) / "b.tar"
        src_b.write_bytes(b"b")
        store.add_switch_mod("title-a", "Mod A", "dev-1", src_a, 1)
        store.add_switch_mod("title-b", "Mod B", "dev-1", src_b, 1)

        assert [m["mod_name"] for m in store.list_switch_mods("title-a")] == ["Mod A"]
        assert [m["mod_name"] for m in store.list_switch_mods("title-b")] == ["Mod B"]


# ── migration ────────────────────────────────────────────────────────────────

def test_migration_22_adds_switch_mods_table():
    """A pre-#444 DB has no switch_mods table at all. Opening it via Store()
    must create it (empty) without disturbing existing data."""
    import sqlite3
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "emusync.db"
        conn = sqlite3.connect(db_path)
        conn.executescript(
            """
            CREATE TABLE devices (id TEXT PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE games (
                slug TEXT PRIMARY KEY, name TEXT NOT NULL,
                console TEXT DEFAULT '', sgdb_game_id INTEGER,
                switch_title_id TEXT NOT NULL DEFAULT ''
            );
            """
        )
        conn.execute("PRAGMA user_version = 21")
        conn.commit()
        conn.close()

        store = Store(tmpdir)

        assert store._conn.execute("PRAGMA user_version").fetchone()[0] >= 22
        tables = {r[0] for r in store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "switch_mods" in tables
        assert store.list_switch_mods("anything") == []


# ── API ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_switch_mods_list_empty_pool(client):
    r = await client.get("/switch/0100000011D90000/mods", headers=AUTH)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_switch_mods_pull_missing_returns_204(client):
    r = await client.get("/switch/0100000011D90000/mods/Nope", headers=AUTH)
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_switch_mods_push_list_pull_roundtrip(client):
    r = await client.post(
        "/switch/0100000011D90000/mods/Cool%20Mod",
        content=b"mod tar bytes",
        headers={**AUTH, "Content-Type": "application/octet-stream"},
    )
    assert r.status_code == 200
    assert r.json()["added"] is True

    r = await client.get("/switch/0100000011D90000/mods", headers=AUTH)
    assert r.status_code == 200
    mods = r.json()
    assert len(mods) == 1
    assert mods[0]["mod_name"] == "Cool Mod"
    assert mods[0]["size"] == len(b"mod tar bytes")

    r = await client.get("/switch/0100000011D90000/mods/Cool%20Mod", headers=AUTH)
    assert r.status_code == 200
    assert r.content == b"mod tar bytes"


@pytest.mark.asyncio
async def test_switch_mods_second_push_is_a_noop(client):
    await client.post(
        "/switch/0100000011D90000/mods/Cool%20Mod",
        content=b"original",
        headers={**AUTH, "Content-Type": "application/octet-stream"},
    )
    r = await client.post(
        "/switch/0100000011D90000/mods/Cool%20Mod",
        content=b"a totally different upload",
        headers={**AUTH, "Content-Type": "application/octet-stream"},
    )
    assert r.status_code == 200
    assert r.json()["added"] is False

    r = await client.get("/switch/0100000011D90000/mods/Cool%20Mod", headers=AUTH)
    assert r.content == b"original"  # untouched by the second push


# ── SyncClient (real sockets, mirrors test_transfer_wizard.py's live_server) ───

def test_sync_client_push_pull_switch_mod(live_server, tmp_path):
    client = SyncClient(live_server["host"], live_server["port"], "", "dev-1", "PC")

    mod_folder = tmp_path / "Cool Mod"
    mod_folder.mkdir()
    (mod_folder / "romfs").mkdir()
    (mod_folder / "romfs" / "file.bin").write_bytes(b"mod content")

    added = client.push_switch_mod("0100000011D90000", "Cool Mod", str(mod_folder))
    assert added is True

    dest = tmp_path / "pulled" / "Cool Mod"
    pulled = client.pull_switch_mod("0100000011D90000", "Cool Mod", str(dest))
    assert pulled is True
    assert (dest / "romfs" / "file.bin").read_bytes() == b"mod content"

    mods = client.list_switch_mods("0100000011D90000")
    assert [m["mod_name"] for m in mods] == ["Cool Mod"]


# ── local ↔ pool name-only sync (cli/run_switch.py) ─────────────────────────────

def test_local_switch_mods_lists_subfolders_across_both_roots(monkeypatch, tmp_path):
    root_a = tmp_path / "root_a"
    root_b = tmp_path / "root_b"
    (root_a / "0100000011D90000" / "Mod One").mkdir(parents=True)
    (root_b / "0100000011D90000" / "Mod Two").mkdir(parents=True)
    monkeypatch.setattr("cli.run_switch._SWITCH_LOAD_ROOTS", (root_a, root_b))

    mods = _local_switch_mods("0100000011D90000")

    assert set(mods.keys()) == {"Mod One", "Mod Two"}
    assert mods["Mod One"] == root_a / "0100000011D90000" / "Mod One"


def test_local_switch_mods_empty_when_no_title_folder(monkeypatch, tmp_path):
    monkeypatch.setattr("cli.run_switch._SWITCH_LOAD_ROOTS", (tmp_path / "root",))
    assert _local_switch_mods("deadbeef00000000") == {}


def test_switch_load_root_for_prefers_root_with_existing_title_folder(monkeypatch, tmp_path):
    root_a = tmp_path / "root_a"
    root_b = tmp_path / "root_b"
    root_a.mkdir()
    (root_b / "0100000011D90000").mkdir(parents=True)
    monkeypatch.setattr("cli.run_switch._SWITCH_LOAD_ROOTS", (root_a, root_b))

    assert _switch_load_root_for("0100000011D90000") == root_b


def test_switch_load_root_for_falls_back_to_any_existing_root(monkeypatch, tmp_path):
    root_a = tmp_path / "root_a"
    root_b = tmp_path / "root_b"
    root_b.mkdir()  # exists, but has no title folder for this game yet
    monkeypatch.setattr("cli.run_switch._SWITCH_LOAD_ROOTS", (root_a, root_b))

    assert _switch_load_root_for("0100000011D90000") == root_b


def test_switch_load_root_for_defaults_to_primary_when_nothing_exists(monkeypatch, tmp_path):
    root_a = tmp_path / "root_a"
    root_b = tmp_path / "root_b"
    monkeypatch.setattr("cli.run_switch._SWITCH_LOAD_ROOTS", (root_a, root_b))

    assert _switch_load_root_for("0100000011D90000") == root_a


class _FakeModClient:
    def __init__(self, pool, fail_pull=frozenset(), fail_push=frozenset()):
        self._pool = pool
        self._fail_pull = fail_pull
        self._fail_push = fail_push
        self.pushed: list[tuple[str, str, str]] = []
        self.pulled: list[tuple[str, str, str]] = []

    def list_switch_mods(self, title_id):
        return [{"mod_name": n} for n in self._pool]

    def push_switch_mod(self, title_id, mod_name, folder):
        if mod_name in self._fail_push:
            raise RuntimeError("boom")
        self.pushed.append((title_id, mod_name, folder))
        return True

    def pull_switch_mod(self, title_id, mod_name, dest):
        if mod_name in self._fail_pull:
            raise RuntimeError("boom")
        self.pulled.append((title_id, mod_name, dest))
        return True


def test_sync_switch_mods_pushes_local_only_and_pulls_pool_only(monkeypatch, tmp_path):
    root = tmp_path / "root"
    (root / "0100000011D90000" / "Local Only").mkdir(parents=True)
    (root / "0100000011D90000" / "Shared Mod").mkdir(parents=True)
    monkeypatch.setattr("cli.run_switch._SWITCH_LOAD_ROOTS", (root,))

    client = _FakeModClient(pool=["Shared Mod", "Pool Only"])

    pushed, pulled = _sync_switch_mods(client, "0100000011D90000")

    assert pushed == ["Local Only"]
    assert pulled == ["Pool Only"]
    # "Shared Mod" exists on both sides by name — never transferred either way.
    assert all(p[1] != "Shared Mod" for p in client.pushed)
    assert all(p[1] != "Shared Mod" for p in client.pulled)


def test_sync_switch_mods_returns_empty_for_blank_title_id():
    client = _FakeModClient(pool=["Something"])
    assert _sync_switch_mods(client, "") == ([], [])
    assert client.pushed == [] and client.pulled == []


def test_sync_switch_mods_tolerates_individual_failures(monkeypatch, tmp_path):
    root = tmp_path / "root"
    (root / "0100000011D90000" / "Bad Push").mkdir(parents=True)
    (root / "0100000011D90000" / "Good Push").mkdir(parents=True)
    monkeypatch.setattr("cli.run_switch._SWITCH_LOAD_ROOTS", (root,))

    client = _FakeModClient(pool=["Bad Pull", "Good Pull"], fail_push={"Bad Push"}, fail_pull={"Bad Pull"})

    pushed, pulled = _sync_switch_mods(client, "0100000011D90000")

    assert pushed == ["Good Push"]
    assert pulled == ["Good Pull"]


def test_sync_switch_mods_never_raises_when_pool_listing_fails():
    class _BrokenClient:
        def list_switch_mods(self, title_id):
            raise RuntimeError("server unreachable")

    assert _sync_switch_mods(_BrokenClient(), "0100000011D90000") == ([], [])
