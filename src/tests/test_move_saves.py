"""Emulator switch save moves (#753): src/gui/electron/emulator/moveSaves.ts run
through Node (type stripping) on real files. Never overwrites, moves state files
individually, no-ops on missing or identical sources. The EXDEV copy branch
needs two filesystems and is covered by the manual script, not here."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[1] / "gui" / "electron" / "emulator" / "moveSaves.ts"


def _node_ok() -> bool:
    node = shutil.which("node")
    if not node:
        return False
    ver = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip().lstrip("v")
    major, minor = (int(x) for x in ver.split(".")[:2])
    return (major, minor) >= (22, 18)  # default type stripping


pytestmark = pytest.mark.skipif(not _node_ok(), reason="needs node >= 22.18")


def _move(**params) -> dict:
    driver = (
        f"const m = await import({json.dumps(MODULE.as_uri())});"
        "console.log(JSON.stringify(m.moveSaves(JSON.parse(process.argv[1]))));"
    )
    out = subprocess.run(
        ["node", "--no-warnings", "--input-type=module", "-e", driver, json.dumps(params)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def test_save_file_moves_to_new_folder(tmp_path):
    src = tmp_path / "ra" / "saves" / "Game" / "Game.srm"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"save-data")
    dest = tmp_path / "mgba" / "Game.sav"
    res = _move(fromSave=str(src), toSave=str(dest))
    assert res["ok"] and res["moved"] == [str(dest)]
    assert dest.read_bytes() == b"save-data"
    assert not src.exists()


def test_folder_save_moves_whole(tmp_path):
    src = tmp_path / "old" / "GC"
    (src / "USA").mkdir(parents=True)
    (src / "USA" / "card.gci").write_bytes(b"gci")
    dest = tmp_path / "new" / "GC"
    res = _move(fromSave=str(src), toSave=str(dest))
    assert res["ok"]
    assert (dest / "USA" / "card.gci").read_bytes() == b"gci"
    assert not src.exists()


def test_state_files_move_individually_and_keep_existing(tmp_path):
    old, new = tmp_path / "old_states", tmp_path / "new_states"
    old.mkdir()
    new.mkdir()
    (old / "Game.state1").write_bytes(b"one")
    (old / "Game.state2").write_bytes(b"two-old")
    (new / "Game.state2").write_bytes(b"two-new")
    res = _move(fromState=str(old), toState=str(new))
    assert res["ok"]
    assert (new / "Game.state1").read_bytes() == b"one"
    # Collision: destination kept, source left in place, reported as skipped.
    assert (new / "Game.state2").read_bytes() == b"two-new"
    assert (old / "Game.state2").read_bytes() == b"two-old"
    assert res["skipped"] == [str(new / "Game.state2")]


def test_existing_destination_never_overwritten(tmp_path):
    src, dest = tmp_path / "a.srm", tmp_path / "b" / "a.sav"
    src.write_bytes(b"old")
    dest.parent.mkdir()
    dest.write_bytes(b"new-emulator-save")
    res = _move(fromSave=str(src), toSave=str(dest))
    assert res["ok"] and res["moved"] == [] and res["skipped"] == [str(dest)]
    assert dest.read_bytes() == b"new-emulator-save"
    assert src.read_bytes() == b"old"


def test_noops_same_missing_and_blank(tmp_path):
    same = tmp_path / "s.srm"
    same.write_bytes(b"x")
    assert _move(fromSave=str(same), toSave=str(same)) == {"ok": True, "moved": [], "skipped": []}
    assert _move(fromSave=str(tmp_path / "none.srm"), toSave=str(tmp_path / "n.sav")) == {"ok": True, "moved": [], "skipped": []}
    # Blank halves (shared-layout per-game switch keeps the card) are skipped.
    assert _move(fromSave="", toSave="", fromState="", toState=str(tmp_path / "st")) == {"ok": True, "moved": [], "skipped": []}
    assert same.read_bytes() == b"x"
    assert not (tmp_path / "n.sav").exists()
