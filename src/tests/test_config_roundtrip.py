"""server/config.py load/save round-trip for art_type_by_console (issue #324)."""
from __future__ import annotations

import server.config as cfg_module


def test_art_type_by_console_defaults_to_empty_dict():
    cfg = cfg_module.Config()
    assert cfg.art_type_by_console == {}


def test_art_type_by_console_roundtrips_through_save_and_load(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg_module, "CONFIG_PATH", tmp_path / "emusync.toml")
    cfg = cfg_module.Config(art_type_by_console={"gba": "grid", "ps2": "hero"})
    cfg_module.save(cfg)

    loaded = cfg_module.load()
    assert loaded.art_type_by_console == {"gba": "grid", "ps2": "hero"}


def test_art_type_by_console_omitted_from_file_when_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg_module, "CONFIG_PATH", tmp_path / "emusync.toml")
    cfg_module.save(cfg_module.Config())
    assert "art_type_by_console" not in (tmp_path / "emusync.toml").read_text()


# ── corruption / atomic write / permissions (#535) ───────────────────────────

def test_corrupt_config_is_backed_up_not_overwritten(tmp_path, monkeypatch):
    path = tmp_path / "emusync.toml"
    monkeypatch.setattr(cfg_module, "CONFIG_PATH", path)
    path.write_text("server_port = [[[ not toml")

    cfg = cfg_module.load()

    assert cfg.server_port == 8765
    backups = list(tmp_path.glob("emusync.toml.corrupt-*"))
    assert len(backups) == 1 and "not toml" in backups[0].read_text()
    assert not path.exists()


def test_bad_port_type_falls_back_to_default(tmp_path, monkeypatch):
    path = tmp_path / "emusync.toml"
    monkeypatch.setattr(cfg_module, "CONFIG_PATH", path)
    path.write_text('server_port = "abc"\n')
    assert cfg_module.load().server_port == 8765


def test_save_is_owner_only_and_leaves_no_tmp(tmp_path, monkeypatch):
    path = tmp_path / "emusync.toml"
    monkeypatch.setattr(cfg_module, "CONFIG_PATH", path)
    cfg_module.save(cfg_module.Config(server_pin="1234"))
    assert (path.stat().st_mode & 0o777) == 0o600
    assert not (tmp_path / "emusync.toml.tmp").exists()
