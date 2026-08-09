"""CLI-level tests for `emusync game pull-switch-save` (#456 follow-up): pulls
the server's Switch save onto a device with no local save yet, and persists
the destination as this device's save_path — backs the GUI's "Pull" button
being usable even when savePath is blank. Follows test_switch_ensure_save_folder.py's
pattern: drives the actual click command via CliRunner against a real uvicorn server.
"""
from __future__ import annotations

from click.testing import CliRunner

import server.config as cfg_module
from cli.game import game_pull_switch_save
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


def test_pulls_server_save_into_local_profile_and_persists_save_path(monkeypatch, tmp_path, live_server):
    title_id = "0100ABF008968000"

    # Device A already has real progress pushed to the server.
    client_a = _device_client(live_server, "dev-a", "DeviceA")
    client_a.add_game("Pokemon Sword", console="Switch", switch_title_id=title_id)
    a_save = tmp_path / "dev_a_save" / title_id
    a_save.mkdir(parents=True)
    (a_save / "save.dat").write_bytes(b"real save data from device A")
    client_a.push_save("pokemon-sword", str(a_save))

    # Device B (the Deck) has never played this game — no local save yet.
    client_b = _device_client(live_server, "dev-b", "DeviceB")
    _write_cfg(monkeypatch, tmp_path, live_server, "dev-b", "DeviceB")

    root = tmp_path / "eden_nand_b"
    (root / "profile-one").mkdir(parents=True)
    monkeypatch.setattr("cli.run_switch._SWITCH_NAND_ROOTS", (root,))

    runner = CliRunner()
    result = runner.invoke(game_pull_switch_save, ["pokemon-sword"])

    assert result.exit_code == 0, result.output
    dest = root / "profile-one" / title_id
    assert (dest / "save.dat").read_bytes() == b"real save data from device A"

    gd = client_b.get_game_device("pokemon-sword")
    assert gd is not None
    assert gd.save_path == str(dest)


def test_errors_when_no_server_save_yet(monkeypatch, tmp_path, live_server):
    client_a = _device_client(live_server, "dev-a", "DeviceA")
    client_a.add_game("Chrono Trigger 2 Switch", console="Switch", switch_title_id="0100ABF008968001")
    _write_cfg(monkeypatch, tmp_path, live_server, "dev-a", "DeviceA")

    root = tmp_path / "eden_nand"
    (root / "profile-one").mkdir(parents=True)
    monkeypatch.setattr("cli.run_switch._SWITCH_NAND_ROOTS", (root,))

    runner = CliRunner()
    result = runner.invoke(game_pull_switch_save, ["chrono-trigger-2-switch"])

    assert result.exit_code != 0
    assert "No save on the server yet" in result.output


def test_preserves_other_device_config_fields(monkeypatch, tmp_path, live_server):
    title_id = "0100ABF008968002"
    client_a = _device_client(live_server, "dev-a", "DeviceA")
    client_a.add_game("Test Switch Game", console="Switch", switch_title_id=title_id)
    a_save = tmp_path / "dev_a_save2" / title_id
    a_save.mkdir(parents=True)
    (a_save / "save.dat").write_bytes(b"data")
    client_a.push_save("test-switch-game", str(a_save))

    client_b = _device_client(live_server, "dev-b", "DeviceB")
    _write_cfg(monkeypatch, tmp_path, live_server, "dev-b", "DeviceB")
    client_b.set_game_device("test-switch-game", GameDeviceConfig(
        rom_path="/roms/switch/Test Switch Game/game.nsp",
        save_path="",
        launch_command="eden %ROM%",
    ))

    root = tmp_path / "eden_nand_b2"
    (root / "profile-one").mkdir(parents=True)
    monkeypatch.setattr("cli.run_switch._SWITCH_NAND_ROOTS", (root,))

    runner = CliRunner()
    result = runner.invoke(game_pull_switch_save, ["test-switch-game"])

    assert result.exit_code == 0, result.output
    gd = client_b.get_game_device("test-switch-game")
    assert gd.rom_path == "/roms/switch/Test Switch Game/game.nsp"
    assert gd.launch_command == "eden %ROM%"
