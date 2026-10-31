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


def test_import_ignored_roms_defaults_to_empty_dict():
    assert cfg_module.Config().import_ignored_roms == {}


def test_import_ignored_roms_roundtrips_through_save_and_load(tmp_path, monkeypatch):
    """The ignore list must survive a Python config rewrite (#646, #499)."""
    monkeypatch.setattr(cfg_module, "CONFIG_PATH", tmp_path / "emusync.toml")
    ignored = {"gba": ["/roms/a b.gba", "C:\\roms\\c.gba"], "snes": ["/roms/s.sfc"]}
    cfg_module.save(cfg_module.Config(import_ignored_roms=ignored))
    assert cfg_module.load().import_ignored_roms == ignored


def test_import_ignored_roms_omitted_from_file_when_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg_module, "CONFIG_PATH", tmp_path / "emusync.toml")
    cfg_module.save(cfg_module.Config())
    assert "import_ignored_roms" not in (tmp_path / "emusync.toml").read_text()


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


# ── device_id backup (#656) ───────────────────────────────────────────────────

def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg_module, "CONFIG_PATH", tmp_path / "emusync.toml")
    monkeypatch.setenv("EMUSYNC_DATA_DIR", str(tmp_path / "data"))


def test_save_writes_device_id_backup(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    cfg = cfg_module.Config()
    cfg_module.save(cfg)
    backup = tmp_path / "data" / "device_id"
    assert backup.read_text() == cfg.device_id
    assert (backup.stat().st_mode & 0o777) == 0o600
    assert not (tmp_path / "data" / "device_id.tmp").exists()


def test_missing_or_corrupt_toml_restores_device_id(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    cfg = cfg_module.Config()
    cfg_module.save(cfg)

    (tmp_path / "emusync.toml").unlink()
    assert cfg_module.load().device_id == cfg.device_id

    (tmp_path / "emusync.toml").write_text("server_port = [[[ not toml")
    assert cfg_module.load().device_id == cfg.device_id


def test_invalid_device_id_backup_is_ignored(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "device_id").write_text("not-a-uuid")
    import uuid
    uuid.UUID(cfg_module.load().device_id)  # fresh, valid UUID
