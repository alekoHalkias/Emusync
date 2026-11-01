"""Incoming ROM transfers may only land inside configured ROM folders (#705)."""
from __future__ import annotations

import os

from cli.transfer import _destination_allowed, _receive_transfer


class _Client:
    def __init__(self, consoles, games=()):
        self.consoles, self.games, self.completed, self.downloaded = consoles, list(games), [], []

    _headers = {"X-Device-ID": "me"}

    def get_device_consoles(self, _id):
        return self.consoles

    def list_my_game_devices(self):
        return self.games

    def download_transfer(self, tid, dest, expected_hash=None):
        self.downloaded.append(dest)
        open(dest, "wb").close()

    def complete_transfer(self, tid, status="completed"):
        self.completed.append(status)


def test_allowed_and_rejected(tmp_path):
    root = str(tmp_path / "roms")
    os.makedirs(root)
    roots = [(root, False)]
    assert _destination_allowed(os.path.join(root, "g", "a.gba"), roots)
    assert not _destination_allowed(os.path.join(root, "..", "evil.gba"), roots)
    assert not _destination_allowed(str(tmp_path / "other" / "a.gba"), roots)
    assert not _destination_allowed("relative/a.gba", roots)
    assert not _destination_allowed(root, roots)
    assert not _destination_allowed(os.path.join(root, ".."), roots)


def test_rom_folder_never_targets_console_root(tmp_path):
    root = str(tmp_path / "roms")
    os.makedirs(root)
    assert not _destination_allowed(os.path.join(root, "a.nsp"), [(root, False)], folder=True)
    assert _destination_allowed(os.path.join(root, "Game", "a.nsp"), [(root, False)], folder=True)
    game = str(tmp_path / "roms" / "Game")
    assert _destination_allowed(os.path.join(game, "a.nsp"), [(game, True)], folder=True)


def test_symlink_escape_rejected(tmp_path):
    root = tmp_path / "roms"
    root.mkdir()
    (tmp_path / "outside").mkdir()
    (root / "link").symlink_to(tmp_path / "outside")
    assert not _destination_allowed(str(root / "link" / "a.gba"), [(str(root), False)])


def test_receive_rejects_outside_destination(tmp_path):
    root = tmp_path / "roms"
    root.mkdir()
    client = _Client([{"device_game_folder": str(root)}])
    logs = []
    ok = _receive_transfer(client, "t1", str(tmp_path / "evil.gba"), "s", "GBA", "G", logs.append)
    assert ok is False and client.downloaded == [] and client.completed == ["failed"]
    assert any("not inside a ROM folder" in m for m in logs)
    _receive_transfer(client, "t2", str(root / "a.gba"), "s", "", "G", logs.append)
    assert client.downloaded == [str(root / "a.gba")]
