"""Device removal keeps saves and leaks no blob files (#750).

A removed device's generations are re-credited to the hidden REMOVED_DEVICE_ID;
only its newest per game / console survives, older ones lose row and file.
"""
from __future__ import annotations

import hashlib
import sqlite3

import pytest

from server.store import Store, schema
from server.store.devices import REMOVED_DEVICE_ID
from tests.conftest import AUTH, _device_auth


def _store(tmp_path) -> Store:
    s = Store(str(tmp_path / "data"))
    s.ensure_device("A", "PC")
    s.ensure_device("B", "Deck")
    s.add_game("zelda", "Zelda", "GBA")
    return s


def _rows(store, table, owner="game_slug", key="zelda"):
    return store._conn.execute(
        f"SELECT id, device_id, hash FROM {table} WHERE {owner} = ? ORDER BY rowid", (key,)
    ).fetchall()


def _files(store, table) -> set[str]:
    d = store._blob_dir / table
    return {p.name for p in d.iterdir() if p.is_file()} if d.is_dir() else set()


def _card(store, tmp_path, device, data: bytes) -> None:
    src = tmp_path / f"card-{hashlib.md5(data).hexdigest()}"
    src.write_bytes(data)
    store.push_console_save_file("PS2", device, src, hashlib.sha256(data).hexdigest(), len(data))


def test_remove_keeps_newest_generation_per_game(tmp_path):
    s = _store(tmp_path)
    for v in (b"a1", b"a2", b"a3"):
        s.push_save("zelda", "A", v)
    for v in (b"s1", b"s2"):
        s.push_state("zelda", "A", v)
    s.push_save("zelda", "B", b"b1")  # current save is B's

    s.remove_device("A")

    saves = _rows(s, "saves")
    assert [(r["device_id"], r["hash"]) for r in saves] == [
        (REMOVED_DEVICE_ID, hashlib.sha256(b"a3").hexdigest()), ("B", hashlib.sha256(b"b1").hexdigest())]
    states = _rows(s, "states")
    assert [(r["device_id"], r["hash"]) for r in states] == [(REMOVED_DEVICE_ID, hashlib.sha256(b"s2").hexdigest())]
    # every file has a row and every row a file
    assert _files(s, "saves") == {r["id"] for r in saves}
    assert _files(s, "states") == {r["id"] for r in states}
    assert s.get_save_meta("zelda").hash == hashlib.sha256(b"b1").hexdigest()


def test_removed_devices_current_save_survives(tmp_path):
    s = _store(tmp_path)
    s.push_save("zelda", "A", b"old")
    s.push_save("zelda", "A", b"only-copy")
    s.remove_device("A")
    path, meta = s.pull_save_path("zelda")
    assert path.read_bytes() == b"only-copy"
    assert meta.hash == hashlib.sha256(b"only-copy").hexdigest()


def test_remove_card_and_mod_pusher_no_fk_error(tmp_path):
    s = _store(tmp_path)
    _card(s, tmp_path, "A", b"card-1")
    _card(s, tmp_path, "A", b"card-2")
    mod = tmp_path / "mod.tar"
    mod.write_bytes(b"ES1\0\x01mod")
    s.add_switch_mod("0100ABF008968000", "Cool", "A", mod, 8)

    s.remove_device("A")  # used to fail the console_save_history / switch_mods FK

    cards = _rows(s, "console_save_history", "console_key", "PS2")
    assert [(r["device_id"], r["hash"]) for r in cards] == [(REMOVED_DEVICE_ID, hashlib.sha256(b"card-2").hexdigest())]
    assert _files(s, "console_save_history") == {r["id"] for r in cards}
    pushed_by = s._conn.execute("SELECT pushed_by FROM switch_mods").fetchone()[0]
    assert pushed_by == REMOVED_DEVICE_ID
    assert s.get_switch_mod_path("0100ABF008968000", "Cool").read_bytes() == b"ES1\0\x01mod"


def test_second_removed_device_keeps_only_newest_placeholder_generation(tmp_path):
    s = _store(tmp_path)
    s.push_save("zelda", "A", b"a")
    s.push_save("zelda", "B", b"b")
    s.remove_device("A")
    s.remove_device("B")
    saves = _rows(s, "saves")
    assert [(r["device_id"], r["hash"]) for r in saves] == [(REMOVED_DEVICE_ID, hashlib.sha256(b"b").hexdigest())]
    assert _files(s, "saves") == {saves[0]["id"]}


def test_remove_edge_cases_are_noops(tmp_path):
    s = _store(tmp_path)
    s.push_save("zelda", "A", b"x")
    s.remove_device("nope")
    s.remove_device("A")
    s.remove_device("A")  # twice
    s.remove_device(REMOVED_DEVICE_ID)  # the placeholder itself
    assert len(_rows(s, "saves")) == 1


def test_clear_devices_keeps_saves_and_hides_placeholder(tmp_path):
    s = _store(tmp_path)
    s.push_save("zelda", "A", b"a1")
    s.push_save("zelda", "A", b"a2")
    s.push_save("zelda", "B", b"b1")
    s.clear_devices()
    assert s.list_devices() == []
    saves = _rows(s, "saves")
    assert [r["hash"] for r in saves] == [hashlib.sha256(b"b1").hexdigest()]  # newest placeholder generation
    assert _files(s, "saves") == {r["id"] for r in saves}


@pytest.mark.asyncio
async def test_placeholder_hidden_from_api_and_rejected_by_auth(client):
    other = _device_auth("dev-x", "PC")
    await client.post("/games", json={"name": "Zelda"}, headers=other)
    await client.post("/games/zelda/save", content=b"ES1\0\x00save", headers=other)
    assert (await client.delete("/devices/dev-x", headers=AUTH)).status_code == 200

    ids = {d["id"] for d in (await client.get("/devices", headers=AUTH)).json()}
    assert REMOVED_DEVICE_ID not in ids and "dev-x" not in ids
    r = await client.get("/games/zelda/save", headers=AUTH)
    assert r.status_code == 200 and r.content == b"ES1\0\x00save"
    r = await client.get("/games", headers=_device_auth(REMOVED_DEVICE_ID, "x"))
    assert r.status_code == 400


# ── v37 orphan quarantine ─────────────────────────────────────────────────────

def _seed_v37(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "db"))
    for ddl in (
        "CREATE TABLE saves (id TEXT)", "CREATE TABLE states (id TEXT)",
        "CREATE TABLE console_save_history (id TEXT)", "CREATE TABLE console_saves (console_key TEXT)",
        "CREATE TABLE switch_mods (title_id TEXT, mod_name TEXT)",
    ):
        conn.execute(ddl)
    conn.execute("INSERT INTO saves VALUES ('s-keep')")
    conn.execute("INSERT INTO states VALUES ('t-keep')")
    conn.execute("INSERT INTO console_save_history VALUES ('h-keep')")
    conn.execute("INSERT INTO console_saves VALUES ('PS2')")
    conn.execute("INSERT INTO switch_mods VALUES ('0100A', 'Keep')")
    blobs = tmp_path / "blobs"
    files = {
        "saves/s-keep": b"1", "saves/s-orphan": b"2", "saves/y.part": b"3",
        "states/t-keep": b"4", "states/t-orphan": b"5",
        "console_save_history/h-keep": b"6", "console_save_history/h-orphan": b"7",
        "console_saves/PS2": b"8", "console_saves/GC": b"9",
        "switch_mods/0100A/Keep.tar": b"10", "switch_mods/0100A/Gone.tar": b"11",
        ".uploads/staged": b"12",
    }
    for rel, data in files.items():
        (blobs / rel).parent.mkdir(parents=True, exist_ok=True)
        (blobs / rel).write_bytes(data)
    return conn, blobs, files


def test_v37_quarantines_only_orphans(tmp_path):
    conn, blobs, files = _seed_v37(tmp_path)
    schema._migrate(conn, from_version=36, blob_dir=blobs)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == schema._SCHEMA_VERSION

    orphans = {"saves/s-orphan", "states/t-orphan", "console_save_history/h-orphan",
               "console_saves/GC", "switch_mods/0100A/Gone.tar"}
    for rel, data in files.items():
        if rel in orphans:
            assert not (blobs / rel).exists(), rel
            assert (blobs / ".orphaned" / rel).read_bytes() == data, rel
        else:
            assert (blobs / rel).read_bytes() == data, rel  # row-backed, .part, .uploads untouched

    before = sorted(p.relative_to(blobs).as_posix() for p in blobs.rglob("*") if p.is_file())
    schema._migrate(conn, from_version=36, blob_dir=blobs)  # idempotent
    assert sorted(p.relative_to(blobs).as_posix() for p in blobs.rglob("*") if p.is_file()) == before


def test_v37_skips_missing_tables_and_dirs(tmp_path):
    conn = sqlite3.connect(":memory:")
    (tmp_path / "blobs" / "saves").mkdir(parents=True)
    (tmp_path / "blobs" / "saves" / "x").write_bytes(b"x")
    schema._migrate(conn, from_version=36, blob_dir=tmp_path / "blobs")
    # no saves table: the dir is skipped, never wholesale quarantined
    assert (tmp_path / "blobs" / "saves" / "x").read_bytes() == b"x"
    assert not (tmp_path / "blobs" / ".orphaned").exists()
