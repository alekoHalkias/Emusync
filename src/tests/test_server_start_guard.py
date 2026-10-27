"""`emusync server start` must not flip a paired client into a server."""
from click.testing import CliRunner

import cli.server as cli_server
from cli.server import server_start
from server import config as cfg_module


def _write(monkeypatch, tmp_path, **kwargs):
    monkeypatch.setattr(cfg_module, "CONFIG_PATH", tmp_path / "emusync.toml")
    # Short-circuit past the guard: if it ever lets the start through, the
    # command exits 0 here instead of binding a real socket and hanging.
    monkeypatch.setattr(cli_server, "_is_server_running", lambda _d: (True, 4242))
    cfg = cfg_module.Config(data_dir=str(tmp_path), **kwargs)
    cfg_module.save(cfg)


def test_start_refuses_on_client_paired_to_external_host(monkeypatch, tmp_path):
    _write(monkeypatch, tmp_path, server_host="192.168.4.111", is_server=False)

    result = CliRunner().invoke(server_start)

    assert result.exit_code == 1
    assert "192.168.4.111" in result.output
    after = cfg_module.load()
    assert after.is_server is False
    assert after.server_host == "192.168.4.111"
    assert not (tmp_path / ".server_pid").exists()


def test_start_still_initializes_blank_host_config(monkeypatch, tmp_path):
    _write(monkeypatch, tmp_path, server_host="", is_server=False, server_port=1)
    result = CliRunner().invoke(server_start)

    assert result.exit_code == 0, result.output
    assert "initialized" in result.output
    assert cfg_module.load().is_server is True
