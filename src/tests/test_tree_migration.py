"""Schema v38: one-time conversion of stored blobs to the manifest format (#739).

A data dir is seeded with format 0/1/2 blobs, rows, baselines and a conflict as a
v37 server left them, stamped v37, and reopened: real Store, real SQLite."""
from __future__ import annotations

import hashlib
import io
import sqlite3
import tarfile
from datetime import datetime, timezone

from server.blob_tree import verify_blob
from server.store import Store, schema
from tests.conftest import tree, tree_dir

_CARD = {"GAME1/GAME1": b"save1", "GAME1/icon.sys": b"icon"}
_STATE = {"slot0.state": b"state", "sub/slot1.state": b"nested"}


def _tar(files, mode="w") -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode=mode) as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _seed(data_dir):
    """A v37 data dir: legacy raw save, tar card, tar.gz state, tar mod, one bogus
    blob, a stray .part, baselines and a conflict on the old card hash."""
    s = Store(str(data_dir))
    s.add_game("zelda", "Zelda")
    s.ensure_device("dev-1", "PC")
    now = datetime.now(timezone.utc).isoformat()
    card_tar, state_tgz = _tar(_CARD), _tar(_STATE, "w:gz")
    seeds = [("saves", "s0", "game_slug", "zelda", b"ES1\0\x09junk", _sha(b"junk")),  # unknown format, older
             ("saves", "s1", "game_slug", "zelda", b"ES1\0\x00SRAM", _sha(b"SRAM")),
             ("states", "t1", "game_slug", "zelda", b"ES1\0\x02" + state_tgz, _sha(state_tgz)),
             ("console_save_history", "c1", "console_key", "PS2", b"ES1\0\x01" + card_tar, _sha(card_tar))]
    for table, blob_id, col, owner, data, h in seeds:
        s._insert_blob_row(table, owner, "dev-1", h, len(data), now, col,
                           "" if col == "console_key" else None, blob_id)
        s._blob_path(table, blob_id).parent.mkdir(parents=True, exist_ok=True)
        s._blob_path(table, blob_id).write_bytes(data)
    (s._blob_dir / "saves" / "s1.part").write_bytes(b"crashed")
    up = s.new_upload_path()
    up.write_bytes(b"x")
    s.add_switch_mod("0100ABF008968000", "Cool", "dev-1", up, 1)
    s.get_switch_mod_path("0100ABF008968000", "Cool").write_bytes(b"ES1\0\x01" + card_tar)
    s.set_save_sync_baseline("zelda", "dev-1", _sha(b"SRAM"), now)
    s.set_console_save_sync_baseline("PS2", "dev-1", _sha(card_tar), now)
    s._add_conflict("console_save_conflicts", "console_key", "PS2", "dev-1", "dev-2", _sha(card_tar), "other")
    s._conn.execute("PRAGMA user_version = 37")
    s._conn.commit()
    s._conn.close()
    return card_tar


def _snapshot(blob_dir):
    return {p.relative_to(blob_dir).as_posix(): p.read_bytes() for p in blob_dir.rglob("*") if p.is_file()}


def test_v38_converts_blobs_and_remaps_hashes(tmp_path, capsys):
    card_tar = _seed(tmp_path)
    s = Store(str(tmp_path))  # runs v38
    assert s._conn.execute("PRAGMA user_version").fetchone()[0] == schema._SCHEMA_VERSION

    save_path, save = s.pull_save_path("zelda")
    assert save_path.read_bytes() == tree(b"SRAM")
    assert save.hash == _sha(b"SRAM") and save.size == 4  # single-file hash unchanged
    state_path, state = s.pull_state_path("zelda")
    assert state_path.read_bytes() == tree_dir(_STATE)
    assert state.hash == verify_blob(state_path)[1] and state.size == len(b"state") + len(b"nested")

    card_path, card = s.pull_console_save_path("PS2")
    assert card_path.read_bytes() == tree_dir(_CARD)
    new_card_hash = verify_blob(card_path)[1]
    assert card["hash"] == new_card_hash != _sha(card_tar)
    # Baseline and conflict moved with the card, so reconcile sees no divergence.
    assert s.get_console_save_sync_baseline("PS2", "dev-1")["hash"] == new_card_hash
    assert s.get_save_sync_baseline("zelda", "dev-1")["hash"] == _sha(b"SRAM")
    row = s._conn.execute("SELECT winner_hash, loser_hash FROM console_save_conflicts").fetchone()
    assert (row["winner_hash"], row["loser_hash"]) == (new_card_hash, "other")

    mod = s.get_switch_mod_path("0100ABF008968000", "Cool")
    assert mod.read_bytes() == tree_dir(_CARD)
    assert s.list_switch_mods("0100ABF008968000")[0]["size"] == len(b"save1") + len(b"icon")

    # Originals kept, DB backed up, the bogus blob and the stray .part untouched.
    blobs = s._blob_dir
    assert (blobs / ".pre-v38" / "saves" / "s1").read_bytes() == b"ES1\0\x00SRAM"
    assert (blobs / ".pre-v38" / "console_save_history" / "c1").read_bytes() == b"ES1\0\x01" + card_tar
    assert (blobs / "saves" / "s0").read_bytes() == b"ES1\0\x09junk"
    assert (blobs / "saves" / "s1.part").read_bytes() == b"crashed"
    backup = sqlite3.connect(str(tmp_path / "emusync.db.pre-v38"))
    assert backup.execute("SELECT hash FROM console_save_history WHERE id = 'c1'").fetchone()[0] == _sha(card_tar)
    err = capsys.readouterr().err
    assert "converted 4 blob(s)" in err and "1 failed" in err


def test_v38_is_idempotent(tmp_path):
    _seed(tmp_path)
    s = Store(str(tmp_path))
    before_files = _snapshot(s._blob_dir)
    before_rows = [tuple(r) for r in s._conn.execute("SELECT id, hash, size FROM console_save_history")]
    schema._migrate(s._conn, from_version=37, blob_dir=s._blob_dir)
    assert _snapshot(s._blob_dir) == before_files
    assert [tuple(r) for r in s._conn.execute("SELECT id, hash, size FROM console_save_history")] == before_rows


def test_restoring_a_converted_generation_keeps_its_new_hash(tmp_path):
    _seed(tmp_path)
    s = Store(str(tmp_path))
    old = s._newest_row("console_save_history", "PS2", "console_key")
    up = s.new_upload_path()
    up.write_bytes(tree(b"newer card"))
    s.push_console_save_file("PS2", "dev-1", up, _sha(b"newer card"), 10)
    meta = s.restore_console_save("PS2", old["id"])
    assert meta["hash"] == old["hash"]
    assert s.integrity_for_console("PS2")["status"] == "ok"
