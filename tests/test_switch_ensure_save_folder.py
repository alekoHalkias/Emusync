"""CLI-level tests for `emusync game ensure-switch-save-folder` (#448, extended
by #453): seeds a real save from the server if another device already pushed
one, otherwise creates an empty <profile>/<title-id>/ placeholder in every
local Eden profile that doesn't already have one. Drives the actual click
command via CliRunner against a real uvicorn server, matching
test_game_remove.py's pattern.
"""
from __future__ import annotations

from click.testing import CliRunner

import server.config as cfg_module
from cli.game import game_ensure_switch_save_folder
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
    )
    cfg_module.save(cfg)
    return cfg


def test_creates_folder_in_every_existing_profile(monkeypatch, tmp_path, live_server):
    client = _device_client(live_server, "dev-a", "DeviceA")
    client.add_game("Pokemon Sword", console="Switch", switch_title_id="0100ABF008968000")
    _write_cfg(monkeypatch, tmp_path, live_server, "dev-a", "DeviceA")

    root = tmp_path / "eden_nand"
    (root / "profile-one").mkdir(parents=True)
    (root / "profile-two").mkdir(parents=True)
    monkeypatch.setattr("cli.run_switch._SWITCH_NAND_ROOTS", (root,))

    runner = CliRunner()
    result = runner.invoke(game_ensure_switch_save_folder, ["pokemon-sword"])

    assert result.exit_code == 0, result.output
    assert (root / "profile-one" / "0100ABF008968000").is_dir()
    assert (root / "profile-two" / "0100ABF008968000").is_dir()
    assert "Created 2 placeholder folder(s)" in result.output


def test_does_not_touch_a_device_that_already_has_a_real_save(monkeypatch, tmp_path, live_server):
    client = _device_client(live_server, "dev-a", "DeviceA")
    client.add_game("Pokemon Sword", console="Switch", switch_title_id="0100ABF008968000")
    _write_cfg(monkeypatch, tmp_path, live_server, "dev-a", "DeviceA")

    root = tmp_path / "eden_nand"
    existing = root / "profile-one" / "0100ABF008968000"
    existing.mkdir(parents=True)
    marker = existing / "already_here.bin"
    marker.write_bytes(b"real save data")
    monkeypatch.setattr("cli.run_switch._SWITCH_NAND_ROOTS", (root,))

    runner = CliRunner()
    result = runner.invoke(game_ensure_switch_save_folder, ["pokemon-sword"])

    assert result.exit_code == 0, result.output
    assert marker.exists()  # untouched, not wiped by a redundant mkdir/seed
    assert "Already has a real save" in result.output


def test_seeds_an_existing_server_save_instead_of_a_placeholder(monkeypatch, tmp_path, live_server):
    # Device B already pushed a real save up to the server.
    dev_b = _device_client(live_server, "dev-b", "DeviceB")
    dev_b.add_game("Pokemon Sword", console="Switch", switch_title_id="0100ABF008968000")
    save_src = tmp_path / "dev_b_save"
    save_src.mkdir()
    (save_src / "save.dat").write_bytes(b"real progress")
    dev_b.push_save("pokemon-sword", str(save_src))

    # Device A has never played it — no local save anywhere yet.
    _device_client(live_server, "dev-a", "DeviceA")
    _write_cfg(monkeypatch, tmp_path, live_server, "dev-a", "DeviceA")

    root = tmp_path / "eden_nand"
    (root / "profile-one").mkdir(parents=True)
    monkeypatch.setattr("cli.run_switch._SWITCH_NAND_ROOTS", (root,))

    runner = CliRunner()
    result = runner.invoke(game_ensure_switch_save_folder, ["pokemon-sword"])

    assert result.exit_code == 0, result.output
    dest = root / "profile-one" / "0100ABF008968000" / "save.dat"
    assert dest.read_bytes() == b"real progress"
    assert "Seeded existing save into 1 folder(s)" in result.output


def test_falls_back_to_a_placeholder_when_server_has_no_save_either(monkeypatch, tmp_path, live_server):
    client = _device_client(live_server, "dev-a", "DeviceA")
    client.add_game("Pokemon Sword", console="Switch", switch_title_id="0100ABF008968000")
    _write_cfg(monkeypatch, tmp_path, live_server, "dev-a", "DeviceA")

    root = tmp_path / "eden_nand"
    (root / "profile-one").mkdir(parents=True)
    monkeypatch.setattr("cli.run_switch._SWITCH_NAND_ROOTS", (root,))

    runner = CliRunner()
    result = runner.invoke(game_ensure_switch_save_folder, ["pokemon-sword"])

    assert result.exit_code == 0, result.output
    dest = root / "profile-one" / "0100ABF008968000"
    assert dest.is_dir()
    assert not any(dest.iterdir())  # empty placeholder, nothing to seed
    assert "Created 1 placeholder folder(s)" in result.output


def test_errors_for_non_switch_game(monkeypatch, tmp_path, live_server):
    client = _device_client(live_server, "dev-a", "DeviceA")
    client.add_game("Chrono Trigger", console="SNES")
    _write_cfg(monkeypatch, tmp_path, live_server, "dev-a", "DeviceA")

    runner = CliRunner()
    result = runner.invoke(game_ensure_switch_save_folder, ["chrono-trigger"])

    assert result.exit_code != 0
    assert "not a managed game" in result.output or "mods only apply to Switch" in result.output


def test_errors_when_title_id_unknown(monkeypatch, tmp_path, live_server):
    client = _device_client(live_server, "dev-a", "DeviceA")
    client.add_game("Some Switch Game", console="Switch")
    _write_cfg(monkeypatch, tmp_path, live_server, "dev-a", "DeviceA")

    runner = CliRunner()
    result = runner.invoke(game_ensure_switch_save_folder, ["some-switch-game"])

    assert result.exit_code != 0
    assert "no known Switch title ID" in result.output
