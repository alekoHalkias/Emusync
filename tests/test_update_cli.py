"""CLI-level tests for `emusync update` (cli/update.py, #441): managing Switch
update/DLC files in a per-game folder, separate from the game's ROM, pushed to
another device via the same rom-transfer pipe ROMs use (tagged kind='update').
"""
from __future__ import annotations

from click.testing import CliRunner

import server.config as cfg_module
from cli.update import add_update, list_updates, push_update
from server.sync_client import SyncClient


def _device_client(live_server, device_id: str, device_name: str) -> SyncClient:
    return SyncClient(live_server["host"], live_server["port"], "", device_id, device_name)


def _write_cfg(monkeypatch, tmp_path, live_server, device_id: str, device_name: str):
    cfg_path = tmp_path / f"{device_id}.toml"
    monkeypatch.setattr(cfg_module, "CONFIG_PATH", cfg_path)
    cfg = cfg_module.Config(
        server_host=live_server["host"],
        server_port=live_server["port"],
        device_id=device_id,
        device_name=device_name,
        data_dir=str(tmp_path / device_id / "data"),
    )
    cfg_module.save(cfg)
    return cfg


def test_add_and_list_managed_update_file(monkeypatch, tmp_path, live_server):
    """add copies the file into the managed per-game folder; list shows it."""
    client = _device_client(live_server, "dev-a", "PC")
    client.add_game("Pokemon Brilliant Diamond", console="Switch")
    _write_cfg(monkeypatch, tmp_path, live_server, "dev-a", "PC")

    update_file = tmp_path / "update.nsp"
    update_file.write_bytes(b"UPDATEDATA")

    runner = CliRunner()
    result = runner.invoke(add_update, [
        "pokemon-brilliant-diamond", str(update_file),
    ])
    assert result.exit_code == 0, result.output
    assert "Added update.nsp" in result.output

    managed_dir = tmp_path / "dev-a" / "data" / "switch_updates" / "pokemon-brilliant-diamond"
    assert (managed_dir / "update.nsp").read_bytes() == b"UPDATEDATA"

    result = runner.invoke(list_updates, ["pokemon-brilliant-diamond"])
    assert result.exit_code == 0, result.output
    assert "update.nsp" in result.output


def test_list_reports_none_when_empty(monkeypatch, tmp_path, live_server):
    client = _device_client(live_server, "dev-b", "PC")
    client.add_game("Some Game", console="Switch")
    _write_cfg(monkeypatch, tmp_path, live_server, "dev-b", "PC")

    result = CliRunner().invoke(list_updates, ["some-game"])
    assert result.exit_code == 0, result.output
    assert "No update files managed" in result.output


def test_push_update_queues_a_kind_tagged_transfer(monkeypatch, tmp_path, live_server):
    """push sends the managed file to another device tagged kind='update', not
    'rom' — so the receiving side never mistakes it for the game's ROM."""
    source = _device_client(live_server, "dev-src", "PC")
    source.add_game("Pokemon Brilliant Diamond", console="Switch")
    _write_cfg(monkeypatch, tmp_path, live_server, "dev-src", "PC")

    target = _device_client(live_server, "dev-dst", "Steam Deck")
    target.list_devices()  # any authed call registers + marks the device online

    update_file = tmp_path / "update.nsp"
    update_file.write_bytes(b"UPDATEDATA")
    runner = CliRunner()
    runner.invoke(add_update, ["pokemon-brilliant-diamond", str(update_file)])

    result = runner.invoke(push_update, ["pokemon-brilliant-diamond", "update.nsp"], input="1\n")
    assert result.exit_code == 0, result.output
    assert "Pushed to Steam Deck" in result.output

    pending = target.list_pending_transfers()
    assert len(pending) == 1
    assert pending[0]["kind"] == "update"
    assert pending[0]["slug"] == "pokemon-brilliant-diamond"


def test_push_update_missing_local_file_errors(monkeypatch, tmp_path, live_server):
    client = _device_client(live_server, "dev-c", "PC")
    client.add_game("Some Game", console="Switch")
    _write_cfg(monkeypatch, tmp_path, live_server, "dev-c", "PC")

    result = CliRunner().invoke(push_update, ["some-game", "missing.nsp"])
    assert result.exit_code != 0
    assert "is not in this device's managed folder" in result.output
