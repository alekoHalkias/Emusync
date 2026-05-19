"""Tests for emusync.config — load/save round-trip and defaults."""
import os
import pytest

from emusync import config as cfg_module
from emusync.config import Config


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Point CONFIG_DIR / CONFIG_FILE at a temporary directory for every test."""
    monkeypatch.setenv("EMUSYNC_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(cfg_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cfg_module, "CONFIG_FILE", tmp_path / "emusync.toml")
    yield


class TestConfigLoad:
    def test_load_creates_file_on_first_run(self, tmp_path):
        cfg = cfg_module.load()
        assert (tmp_path / "emusync.toml").exists()

    def test_load_generates_unique_device_id(self):
        cfg1 = cfg_module.load()
        # Remove the file so a second fresh load is forced in a different dir
        assert len(cfg1.device_id) == 36  # UUID4 string length

    def test_load_sets_device_name(self):
        cfg = cfg_module.load()
        assert cfg.device_name == os.uname().nodename

    def test_load_defaults(self):
        cfg = cfg_module.load()
        assert cfg.server_host == ""
        assert cfg.server_port == 8765
        assert cfg.token == ""
        assert cfg.is_server is False

    def test_load_returns_saved_values(self):
        original = cfg_module.load()
        original.server_host = "192.168.1.10"
        original.server_port = 9000
        original.token = "my-token"
        original.is_server = True
        cfg_module.save(original)

        loaded = cfg_module.load()
        assert loaded.server_host == "192.168.1.10"
        assert loaded.server_port == 9000
        assert loaded.token == "my-token"
        assert loaded.is_server is True

    def test_load_preserves_device_id_across_saves(self):
        cfg = cfg_module.load()
        device_id = cfg.device_id
        cfg_module.save(cfg)
        reloaded = cfg_module.load()
        assert reloaded.device_id == device_id


class TestConfigSave:
    def test_save_creates_config_dir(self, tmp_path):
        nested = tmp_path / "nested" / "deeper"
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(cfg_module, "CONFIG_DIR", nested)
        monkeypatch.setattr(cfg_module, "CONFIG_FILE", nested / "emusync.toml")
        cfg_module.save(Config(device_id="x", device_name="y"))
        assert (nested / "emusync.toml").exists()
        monkeypatch.undo()

    def test_save_and_reload_all_fields(self):
        cfg = Config(
            server_host="10.0.0.1",
            server_port=1234,
            data_dir="/tmp/data",
            device_id="device-uuid",
            device_name="MyPC",
            token="tok-123",
            is_server=True,
        )
        cfg_module.save(cfg)
        loaded = cfg_module.load()
        assert loaded.server_host == "10.0.0.1"
        assert loaded.server_port == 1234
        assert loaded.data_dir == "/tmp/data"
        assert loaded.device_id == "device-uuid"
        assert loaded.device_name == "MyPC"
        assert loaded.token == "tok-123"
        assert loaded.is_server is True
