"""Wii NAND per-title save sync (#431).

Covers `cli.run_wii._resolve_written_wii_save` (pure filesystem logic — which
title folder a play session actually wrote to) and the generalized
`SyncClient.push_save`/`pull_save` (server/sync_client.py) now being
folder-aware, exercised end to end against a real server per this suite's
no-mocks convention.
"""
from __future__ import annotations

import time
from pathlib import Path

from cli.run_wii import _resolve_written_wii_save
from server.sync_client import GameDeviceConfig, SyncClient


def _make_title(nand_root: Path, title_type: str, hex_id: str) -> Path:
    data_dir = nand_root / "title" / title_type / hex_id / "data"
    data_dir.mkdir(parents=True)
    content_dir = nand_root / "title" / title_type / hex_id / "content"
    content_dir.mkdir(parents=True)
    (content_dir / "title.tmd").write_bytes(b"ticket")  # never touched
    return data_dir


def test_resolves_the_single_title_written_this_session(monkeypatch, tmp_path):
    nand_root = tmp_path / "Wii"
    monkeypatch.setattr("cli.run_wii._WII_NAND_ROOTS", (nand_root,))

    data_dir = _make_title(nand_root, "00010000", "52504245")
    since = time.time()
    time.sleep(0.01)
    (data_dir / "setting.txt").write_text("save data")

    result = _resolve_written_wii_save(since)

    assert result == str(data_dir)


def test_ignores_system_titles_and_content_folder(monkeypatch, tmp_path):
    nand_root = tmp_path / "Wii"
    monkeypatch.setattr("cli.run_wii._WII_NAND_ROOTS", (nand_root,))

    # System Menu (00000001/00000002) — must never be adopted as a game save.
    sys_data = nand_root / "title" / "00000001" / "00000002" / "data"
    sys_data.mkdir(parents=True)
    since = time.time()
    time.sleep(0.01)
    (sys_data / "state.dat").write_text("system state")

    result = _resolve_written_wii_save(since)

    assert result is None


def test_returns_none_when_nothing_written_this_session(monkeypatch, tmp_path):
    nand_root = tmp_path / "Wii"
    monkeypatch.setattr("cli.run_wii._WII_NAND_ROOTS", (nand_root,))
    _make_title(nand_root, "00010000", "52504245")  # exists, but untouched

    result = _resolve_written_wii_save(time.time())

    assert result is None


def test_ambiguous_multi_title_write_warns_and_skips(monkeypatch, tmp_path, capsys):
    nand_root = tmp_path / "Wii"
    monkeypatch.setattr("cli.run_wii._WII_NAND_ROOTS", (nand_root,))

    data_a = _make_title(nand_root, "00010000", "52504245")
    data_b = _make_title(nand_root, "00010000", "52424645")
    since = time.time()
    time.sleep(0.01)
    (data_a / "setting.txt").write_text("a")
    (data_b / "setting.txt").write_text("b")

    result = _resolve_written_wii_save(since)

    assert result is None
    assert "multiple Wii titles" in capsys.readouterr().err


def test_push_pull_save_round_trips_a_folder(tmp_path, live_server):
    """SyncClient.push_save/pull_save must handle a folder-shaped save (Dolphin
    Wii/GC), not just a single file, now that they route through
    memcard_bytes/_write_memcard like the console-memcard endpoints already do."""
    client = SyncClient(live_server["host"], live_server["port"], "", "dev-1", "PC")
    client.add_game("Some Wii Game", console="Wii")
    client.set_game_device("some-wii-game", GameDeviceConfig())

    save_dir = tmp_path / "data"
    save_dir.mkdir()
    (save_dir / "setting.txt").write_text("save contents")

    client.push_save("some-wii-game", str(save_dir))

    dest_dir = tmp_path / "dest" / "data"
    pulled, server_hash = client.pull_save("some-wii-game", str(dest_dir))

    assert pulled is True
    assert server_hash is not None
    assert (dest_dir / "setting.txt").read_text() == "save contents"
