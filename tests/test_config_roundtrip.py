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
