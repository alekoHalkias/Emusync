"""One-time conversion of pre-#478 un-enveloped blobs (#738).

The server wraps every legacy blob file in the transfer envelope once (schema
v36) and wraps old-client uploads on arrival, so clients never sniff. Payload
bytes and envelope-free hashes must not change.
"""
from __future__ import annotations

import hashlib
import io
import sqlite3
import tarfile

import pytest
from httpx import ASGITransport, AsyncClient

import server.api as api_module
from server.store import Store, schema
from server.blob_tree import verify_blob
from server.store.blobs import _envelope_file_in_place
from server.sync_client import (
    _ENVELOPE_MAGIC, _FMT_RAW, _FMT_TAR, _FMT_TARGZ,
    _extract_state_folder, _pack_envelope, _write_memcard,
)
from tests.conftest import AUTH, MASTER_PIN, tree, tree_dir


def _tar(files: dict[str, bytes], mode: str = "w") -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode=mode) as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


_TAR = _tar({"GAME1/save.bin": b"card"})
_TGZ = _tar({"slot0.state": b"state"}, "w:gz")

# (data, states, expected format); a plain tar as a state was written raw by the
# old client fallback (it only tried gzip), so it stays raw.
_SHAPES = {
    "raw-save": (b"\x00\x01SRAM", False, _FMT_RAW),
    "tar-card": (_TAR, False, _FMT_TAR),
    "tgz-card": (_TGZ, False, _FMT_TARGZ),
    "tgz-state": (_TGZ, True, _FMT_TARGZ),
    "raw-state": (b"RAWSTATE", True, _FMT_RAW),
    "tar-as-state": (_TAR, True, _FMT_RAW),
}


@pytest.mark.parametrize("name", sorted(_SHAPES))
def test_converter_wraps_each_legacy_shape(tmp_path, name):
    data, states, fmt = _SHAPES[name]
    p = tmp_path / "blob"
    p.write_bytes(data)
    assert _envelope_file_in_place(p, states) is True
    assert p.read_bytes() == _ENVELOPE_MAGIC + bytes([fmt]) + data
    assert not list(tmp_path.glob("*.part"))


def test_converter_leaves_enveloped_blob_alone(tmp_path):
    p = tmp_path / "blob"
    p.write_bytes(_pack_envelope(_FMT_RAW, b"already"))
    assert _envelope_file_in_place(p, False) is False
    assert p.read_bytes() == _pack_envelope(_FMT_RAW, b"already")


def _seed_blobs(blob_dir):
    """One legacy file per table (mods nest one level), one enveloped file, one stray .part."""
    files = {
        "saves/s1": b"SRAM",
        "states/t1": _TGZ,
        "console_save_history/h1": _TAR,
        "console_saves/PS2": b"RAWCARD",
        "switch_mods/0100ABF008968000/mod.tar": _TAR,
        "saves/s2": _pack_envelope(_FMT_RAW, b"new"),
        "saves/s3.part": b"crashed-write",
    }
    for rel, data in files.items():
        (blob_dir / rel).parent.mkdir(parents=True, exist_ok=True)
        (blob_dir / rel).write_bytes(data)
    return files


def test_v36_converts_every_table_once(tmp_path):
    blobs = tmp_path / "blobs"
    files = _seed_blobs(blobs)
    # The v36 step alone: v37 would quarantine these row-less seed files (#750).
    schema._envelope_legacy_blobs(blobs)

    expected = {"saves/s1": _FMT_RAW, "states/t1": _FMT_TARGZ, "console_save_history/h1": _FMT_TAR,
                "console_saves/PS2": _FMT_RAW, "switch_mods/0100ABF008968000/mod.tar": _FMT_TAR}
    for rel, fmt in expected.items():
        assert (blobs / rel).read_bytes() == _ENVELOPE_MAGIC + bytes([fmt]) + files[rel], rel
    assert (blobs / "saves/s2").read_bytes() == files["saves/s2"]  # already enveloped
    assert (blobs / "saves/s3.part").read_bytes() == b"crashed-write"  # not a blob

    before = {p: p.read_bytes() for p in blobs.rglob("*") if p.is_file()}
    schema._envelope_legacy_blobs(blobs)  # idempotent
    assert {p: p.read_bytes() for p in blobs.rglob("*") if p.is_file()} == before


def test_v36_skips_missing_dirs(tmp_path):
    conn = sqlite3.connect(":memory:")
    schema._migrate(conn, from_version=35, blob_dir=tmp_path / "nothing-here")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == schema._SCHEMA_VERSION


@pytest.mark.asyncio
async def test_legacy_blobs_survive_the_full_upgrade_chain(tmp_path):
    """End to end: un-enveloped save + state stored by an old server, DB at v35;
    the upgraded Store runs v36 (envelope) and v38 (manifest, #739). The save keeps
    its hash, the state gets its manifest hash, and the client writes the original
    content."""
    data_dir = tmp_path / "data"
    store = Store(str(data_dir))
    store.add_game("zelda", "Zelda")
    store.ensure_device("dev-old", "Old PC")
    save = b"\xde\xad legacy sram"
    store.push_save("zelda", "dev-old", tree(b"placeholder"))
    store.push_state("zelda", "dev-old", tree(b"placeholder"))
    for table, data in (("saves", save), ("states", _TGZ)):  # what a pre-#478 server stored
        row = store._newest_row(table, "zelda")
        store._blob_path(table, row["id"]).write_bytes(data)
        store._conn.execute(f"UPDATE {table} SET hash = ?, size = ? WHERE id = ?",
                            (hashlib.sha256(data).hexdigest(), len(data), row["id"]))
    store._conn.execute("PRAGMA user_version = 35")
    store._conn.commit()
    store._conn.close()

    api_module.init(Store(str(data_dir)), MASTER_PIN)  # reopen runs v36..v38
    async with AsyncClient(transport=ASGITransport(app=api_module.app), base_url="http://t") as c:
        r = await c.get("/games/zelda/save", headers=AUTH)
        assert r.content == tree(save)
        assert r.headers["x-save-hash"] == hashlib.sha256(save).hexdigest()
        rs = await c.get("/games/zelda/state", headers=AUTH)
        assert rs.content == tree_dir({"slot0.state": b"state"})
        assert rs.headers["x-state-hash"] == verify_blob(rs.content)[1]

    card = tmp_path / "out" / "zelda.srm"
    _write_memcard(card, r.content)
    assert card.read_bytes() == save
    states = tmp_path / "out" / "states"
    _extract_state_folder(rs.content, states)
    assert (states / "slot0.state").read_bytes() == b"state"


@pytest.mark.asyncio
async def test_pre_739_state_and_mod_uploads_are_rejected(client):
    """Old clients' state and mod uploads (bare or format 0-2) get a 400 and
    nothing is stored; they must update after the server (#739)."""
    await client.post("/games", json={"name": "Zelda"}, headers=AUTH)
    for body in (_TGZ, _pack_envelope(_FMT_TARGZ, _TGZ)):
        r = await client.post("/games/zelda/state", content=body, headers=AUTH)
        assert r.status_code == 400
    assert (await client.get("/games/zelda/state", headers=AUTH)).status_code == 204
    for body in (_TAR, _pack_envelope(_FMT_TAR, _TAR)):
        r = await client.post("/switch/0100ABF008968000/mods/Cool", content=body, headers=AUTH)
        assert r.status_code == 400
    assert (await client.get("/switch/0100ABF008968000/mods", headers=AUTH)).json() == []
