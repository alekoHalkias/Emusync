"""Config/data/cache path resolution + the one-time ~/.emusync migration (#564).
Real files in a tmp HOME; no mocks."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import tomlkit

from server import paths


@pytest.fixture
def home(tmp_path, monkeypatch):
    for v in ("EMUSYNC_CONFIG_DIR", "EMUSYNC_DATA_DIR", "EMUSYNC_CACHE_DIR",
              "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(paths.sys, "platform", "linux")
    return tmp_path


def _legacy(home: Path, data_dir_line: bool = True) -> Path:
    old = home / ".emusync"
    (old / "blobs" / "saves").mkdir(parents=True)
    (old / "blobs" / "saves" / "b1").write_bytes(b"save")
    (old / "art" / "consoles").mkdir(parents=True)
    (old / "art" / "consoles" / "gba.png").write_bytes(b"icon")
    (old / "art" / "gba" / "game").mkdir(parents=True)
    (old / "art" / "gba" / "game" / "grid.png").write_bytes(b"grid")
    (old / "emusync.db").write_bytes(b"db")
    (old / "display.json").write_text("{}")
    (old / "switch_titledb.json").write_text("{}")
    (old / "ps2_serials.json").write_text("{}")
    doc = tomlkit.document()
    if data_dir_line:
        doc.add("data_dir", str(old))
    doc.add("device_id", "dev-1")
    (old / "emusync.toml").write_text(tomlkit.dumps(doc))
    return old


def test_linux_defaults_and_xdg_overrides(home, monkeypatch):
    assert paths.config_dir() == home / ".config" / "emusync"
    assert paths.data_dir() == home / ".local" / "share" / "emusync"
    assert paths.cache_dir() == home / ".cache" / "emusync"
    monkeypatch.setenv("XDG_DATA_HOME", str(home / "xd"))
    assert paths.data_dir() == home / "xd" / "emusync"
    monkeypatch.setenv("XDG_DATA_HOME", "relative/ignored")  # XDG says: ignore non-absolute
    assert paths.data_dir() == home / ".local" / "share" / "emusync"
    monkeypatch.setenv("EMUSYNC_DATA_DIR", str(home / "iso"))
    assert paths.data_dir() == home / "iso"


def test_migration_splits_files_and_rewrites_data_dir(home):
    old = _legacy(home)
    assert paths.migrate_legacy() is True
    cfg, data, cache = paths.config_dir(), paths.data_dir(), paths.cache_dir()
    assert (cfg / "emusync.toml").exists() and (cfg / "display.json").exists()
    assert (cache / "switch_titledb.json").exists() and (cache / "consoles" / "gba.png").exists()
    assert (data / "emusync.db").read_bytes() == b"db"
    assert (data / "blobs" / "saves" / "b1").read_bytes() == b"save"
    assert (data / "art" / "gba" / "game" / "grid.png").exists()
    assert (data / "ps2_serials.json").exists()
    assert not (data / "art" / "consoles").exists()
    doc = tomlkit.parse((cfg / "emusync.toml").read_text())
    assert doc["data_dir"] == str(data) and doc["device_id"] == "dev-1"
    assert (old / paths.NOTE_NAME).exists() and not (old / "emusync.db").exists()


def test_migration_keeps_custom_data_dir(home):
    old = _legacy(home, data_dir_line=False)
    toml = old / "emusync.toml"
    toml.write_text(toml.read_text() + 'data_dir = "/mnt/big/emusync"\n')
    paths.migrate_legacy()
    doc = tomlkit.parse((paths.config_dir() / "emusync.toml").read_text())
    assert doc["data_dir"] == "/mnt/big/emusync"


def test_migration_is_idempotent(home):
    _legacy(home)
    assert paths.migrate_legacy() is True
    assert paths.migrate_legacy() is False  # only the breadcrumb note is left


def test_migration_never_overwrites_and_refuses_existing_db(home):
    _legacy(home)
    (paths.data_dir()).mkdir(parents=True)
    (paths.data_dir() / "emusync.db").write_bytes(b"new")
    assert paths.migrate_legacy() is False  # new data dir already has a database
    assert (home / ".emusync" / "emusync.db").read_bytes() == b"db"
    assert (paths.data_dir() / "emusync.db").read_bytes() == b"new"


def test_migration_merge_keeps_existing_target_file(home):
    old = _legacy(home)
    (paths.data_dir() / "blobs" / "saves").mkdir(parents=True)
    (paths.data_dir() / "blobs" / "saves" / "b1").write_bytes(b"newer")
    paths.migrate_legacy()
    assert (paths.data_dir() / "blobs" / "saves" / "b1").read_bytes() == b"newer"
    assert (old / "blobs" / "saves" / "b1").read_bytes() == b"save"  # left behind, not lost


def test_migration_skips_while_old_server_is_running(home):
    old = _legacy(home)
    (old / ".server_pid").write_text(str(os.getpid()))  # a live pid
    assert paths.migrate_legacy() is False
    assert (old / "emusync.db").exists()


def test_migration_noop_with_override_or_no_legacy(home, monkeypatch):
    assert paths.migrate_legacy() is False
    _legacy(home)
    monkeypatch.setenv("EMUSYNC_DATA_DIR", str(home / "iso"))
    assert paths.migrate_legacy() is False
    assert (home / ".emusync" / "emusync.db").exists()


def test_typescript_mirror_agrees_on_linux_defaults():
    src = (Path(__file__).parent.parent / "gui" / "electron" / "paths.ts").read_text()
    for needle in ('"XDG_CONFIG_HOME", ".config"', '"XDG_DATA_HOME", ".local/share"',
                   '"XDG_CACHE_HOME", ".cache"', "EMUSYNC_${kind.toUpperCase()}_DIR",
                   '"Application Support"', '"Caches"', "AppData", '"emusync"'):
        assert needle in src, needle
