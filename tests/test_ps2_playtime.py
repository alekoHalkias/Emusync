"""PCSX2 playtime.dat parsing + PS2 serial learning (issue #301)."""
from __future__ import annotations

import json

import cli.run as run


def test_read_pcsx2_playtime_parses_columns(tmp_path, monkeypatch):
    pt = tmp_path / "playtime.dat"
    pt.write_text(
        "SLUS-20998                       273                  1782864851          \n"
        "SLUS-21021                       23                   1779172522          \n"
    )
    monkeypatch.setattr(run, "_PCSX2_PLAYTIME_FILES", (pt,))
    data = run._read_pcsx2_playtime()
    assert data["SLUS-20998"] == {"seconds": 273, "last_played": 1782864851}
    assert data["SLUS-21021"]["last_played"] == 1779172522


def test_learn_ps2_serial_picks_freshest_session(tmp_path, monkeypatch):
    pt = tmp_path / "playtime.dat"
    pt.write_text("SLUS-20998  273  1782864851\nSLUS-21021  23  1779172522\n")
    monkeypatch.setattr(run, "_PCSX2_PLAYTIME_FILES", (pt,))

    class Cfg:
        data_dir = str(tmp_path)

    # Launch happened after the older game's timestamp → the newest row is ours.
    run._learn_ps2_serial(Cfg(), "jak-3", since=1779172523)
    mapping = json.loads((tmp_path / "ps2_serials.json").read_text())
    assert mapping == {"jak-3": "SLUS-20998"}


def test_learn_ps2_serial_noop_when_nothing_played_this_session(tmp_path, monkeypatch):
    pt = tmp_path / "playtime.dat"
    pt.write_text("SLUS-20998  273  1000\n")
    monkeypatch.setattr(run, "_PCSX2_PLAYTIME_FILES", (pt,))

    class Cfg:
        data_dir = str(tmp_path)

    run._learn_ps2_serial(Cfg(), "x", since=5000)  # no row at/after launch
    assert not (tmp_path / "ps2_serials.json").exists()


def test_learn_ps2_serial_merges_without_clobbering(tmp_path, monkeypatch):
    (tmp_path / "ps2_serials.json").write_text(json.dumps({"other": "SCUS-97330"}))
    pt = tmp_path / "playtime.dat"
    pt.write_text("SLUS-20998  273  1782864851\n")
    monkeypatch.setattr(run, "_PCSX2_PLAYTIME_FILES", (pt,))

    class Cfg:
        data_dir = str(tmp_path)

    run._learn_ps2_serial(Cfg(), "jak-3", since=1000)
    mapping = json.loads((tmp_path / "ps2_serials.json").read_text())
    assert mapping == {"other": "SCUS-97330", "jak-3": "SLUS-20998"}
