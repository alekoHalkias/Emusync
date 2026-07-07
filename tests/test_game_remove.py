"""CLI-level tests for `emusync game remove` (issue #363): default behavior must
unlink the game from the calling device only, leaving other devices and the
game's save/state history untouched; `--everywhere` opts into the full purge.
Drives the actual click command via CliRunner against a real uvicorn server —
no mocks, matching test_transfer_wizard.py's pattern.
"""
from __future__ import annotations

from click.testing import CliRunner

import server.config as cfg_module
from cli.game import game_remove
from server.sync_client import GameDeviceConfig, SyncClient


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
    )
    cfg_module.save(cfg)
    return cfg


def test_remove_default_unlinks_this_device_only(monkeypatch, tmp_path, live_server):
    source = _device_client(live_server, "dev-a", "DeviceA")
    source.add_game("Chrono Trigger", console="SNES")
    source.set_game_device("chrono-trigger", GameDeviceConfig(rom_path="/roms/ct.sfc"))

    other = _device_client(live_server, "dev-b", "DeviceB")
    other.set_game_device("chrono-trigger", GameDeviceConfig(rom_path="/other/ct.sfc"))

    _write_cfg(monkeypatch, tmp_path, live_server, "dev-a", "DeviceA")

    runner = CliRunner()
    result = runner.invoke(game_remove, ["chrono-trigger"], input="y\n")

    assert result.exit_code == 0, result.output
    assert "this device only" in result.output

    # This device's config is gone…
    assert source.get_game_device("chrono-trigger") is None
    # …but the game and the other device's config survive.
    assert source.get_game("chrono-trigger") is not None
    assert other.get_game_device("chrono-trigger") is not None


def test_remove_everywhere_fully_purges(monkeypatch, tmp_path, live_server):
    source = _device_client(live_server, "dev-a", "DeviceA")
    source.add_game("Chrono Trigger", console="SNES")
    source.set_game_device("chrono-trigger", GameDeviceConfig(rom_path="/roms/ct.sfc"))

    other = _device_client(live_server, "dev-b", "DeviceB")
    other.set_game_device("chrono-trigger", GameDeviceConfig(rom_path="/other/ct.sfc"))

    _write_cfg(monkeypatch, tmp_path, live_server, "dev-a", "DeviceA")

    runner = CliRunner()
    result = runner.invoke(game_remove, ["chrono-trigger", "--everywhere"], input="y\n")

    assert result.exit_code == 0, result.output
    assert "every device" in result.output

    assert source.get_game("chrono-trigger") is None
    assert other.get_game_device("chrono-trigger") is None


def test_remove_cancelled_when_not_confirmed(monkeypatch, tmp_path, live_server):
    source = _device_client(live_server, "dev-a", "DeviceA")
    source.add_game("Chrono Trigger", console="SNES")
    source.set_game_device("chrono-trigger", GameDeviceConfig(rom_path="/roms/ct.sfc"))

    _write_cfg(monkeypatch, tmp_path, live_server, "dev-a", "DeviceA")

    runner = CliRunner()
    result = runner.invoke(game_remove, ["chrono-trigger"], input="n\n")

    assert result.exit_code == 0, result.output
    assert "Cancelled" in result.output
    assert source.get_game_device("chrono-trigger") is not None
