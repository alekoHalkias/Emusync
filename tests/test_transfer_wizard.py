"""CLI-level tests for the `push`/`pull` ROM transfer wizards (cli/transfer.py).

These interactive commands had zero test coverage despite being the most
complex CLI flows in the project. Each test runs against a real uvicorn
server (the `live_server` fixture) and drives the actual click commands via
`CliRunner`, matching the "no mocks" philosophy used elsewhere in this suite.
"""
from __future__ import annotations

from click.testing import CliRunner

import server.config as cfg_module
from cli.transfer import _handle_pull_request, _receive_transfer, pull_rom, push_rom
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


def test_push_rom_uploads_to_target_device(monkeypatch, tmp_path, live_server):
    """push wizard: select a local game, pick a target device, confirm a custom
    destination folder, and the server ends up with a queued rom_transfer."""
    rom = tmp_path / "fusion.gba"
    rom.write_bytes(b"ROMDATA" * 200)

    source = _device_client(live_server, "dev-source", "SourcePC")
    source.add_game("Metroid Fusion", console="GBA")
    source.set_game_device(
        "metroid-fusion",
        GameDeviceConfig(rom_path=str(rom), rom_folder_path=str(rom.parent)),
    )

    target = _device_client(live_server, "dev-target", "SteamDeck")
    target.list_devices()  # any authed call registers + marks the device online

    _write_cfg(monkeypatch, tmp_path, live_server, "dev-source", "SourcePC")

    dest_folder = tmp_path / "deck_roms"
    runner = CliRunner()
    result = runner.invoke(push_rom, input=f"1\n1\n{dest_folder}\n")

    assert result.exit_code == 0, result.output
    assert "pushed to SteamDeck" in result.output
    assert "shortly" in result.output

    pending = target.list_pending_transfers()
    assert len(pending) == 1
    assert pending[0]["slug"] == "metroid-fusion"


def test_push_rom_switch_syncs_whole_folder(monkeypatch, tmp_path, live_server):
    """Switch games live one-per-folder: pushing tars up the base ROM's whole
    containing folder (including sibling update/DLC files) instead of just
    the ROM file, and the receiving side extracts all of it into the target
    folder (#441)."""
    game_dir = tmp_path / "switch_roms" / "Pokemon Brilliant Diamond"
    game_dir.mkdir(parents=True)
    rom = game_dir / "pbd.nsp"
    rom.write_bytes(b"BASEROMDATA")
    update = game_dir / "pbd_update.nsp"
    update.write_bytes(b"UPDATEDATA")

    source = _device_client(live_server, "dev-source", "SourcePC")
    source.add_game("Pokemon Brilliant Diamond", console="Switch")
    source.set_game_device(
        "pokemon-brilliant-diamond",
        GameDeviceConfig(rom_path=str(rom), rom_folder_path=str(game_dir.parent)),
    )

    target = _device_client(live_server, "dev-target", "SteamDeck")
    target.list_devices()

    _write_cfg(monkeypatch, tmp_path, live_server, "dev-source", "SourcePC")

    dest_folder = tmp_path / "deck_roms" / "Pokemon Brilliant Diamond"
    runner = CliRunner()
    result = runner.invoke(push_rom, input=f"1\n1\n{dest_folder}\n")

    assert result.exit_code == 0, result.output
    assert "pushed to SteamDeck" in result.output
    assert "whole folder" in result.output

    pending = target.list_pending_transfers()
    assert len(pending) == 1
    assert pending[0]["kind"] == "rom-folder"

    # Simulate the target's sync-daemon receiving the queued transfer.
    ok = _receive_transfer(
        target, pending[0]["id"], pending[0]["destination_path"],
        pending[0]["slug"], pending[0].get("console", ""), pending[0]["game_name"],
        sha256=pending[0].get("sha256"), kind=pending[0]["kind"],
    )
    assert ok

    assert (dest_folder / "pbd.nsp").read_bytes() == b"BASEROMDATA"
    assert (dest_folder / "pbd_update.nsp").read_bytes() == b"UPDATEDATA"

    registered = target.get_game_device("pokemon-brilliant-diamond")
    assert registered.rom_path == str(dest_folder / "pbd.nsp")


def test_pull_rom_requests_from_source_device(monkeypatch, tmp_path, live_server):
    """pull wizard: pick a source device, pick one of its games, confirm a local
    destination folder, and the source ends up with a pending pull request."""
    rom = tmp_path / "fusion.gba"
    rom.write_bytes(b"ROMDATA" * 200)

    source = _device_client(live_server, "dev-source", "SourcePC")
    source.add_game("Metroid Fusion", console="GBA")
    source.set_game_device(
        "metroid-fusion",
        GameDeviceConfig(rom_path=str(rom), rom_folder_path=str(rom.parent)),
    )
    source.list_devices()  # mark source online for the puller's device list

    _write_cfg(monkeypatch, tmp_path, live_server, "dev-target", "SteamDeck")

    dest_folder = tmp_path / "deck_roms"
    runner = CliRunner()
    result = runner.invoke(pull_rom, input=f"1\n1\n{dest_folder}\n")

    assert result.exit_code == 0, result.output
    assert "pulled from SourcePC" in result.output
    assert "shortly" in result.output

    pending = source.list_pending_pull_requests()
    assert len(pending) == 1
    assert pending[0]["slug"] == "metroid-fusion"
    assert pending[0]["destination_path"] == str(dest_folder / "fusion.gba")


def test_pull_rom_switch_syncs_whole_folder(monkeypatch, tmp_path, live_server):
    """Symmetric with the push side (#441): pulling a Switch game requests a
    'rom-folder' kind pull; fulfilling it tars the source device's whole game
    folder (base ROM + sibling update/DLC files) rather than just the ROM."""
    game_dir = tmp_path / "switch_roms" / "Pokemon Brilliant Diamond"
    game_dir.mkdir(parents=True)
    rom = game_dir / "pbd.nsp"
    rom.write_bytes(b"BASEROMDATA")
    update = game_dir / "pbd_update.nsp"
    update.write_bytes(b"UPDATEDATA")

    source = _device_client(live_server, "dev-source", "SourcePC")
    source.add_game("Pokemon Brilliant Diamond", console="Switch")
    source.set_game_device(
        "pokemon-brilliant-diamond",
        GameDeviceConfig(rom_path=str(rom), rom_folder_path=str(game_dir.parent)),
    )
    source.list_devices()

    _write_cfg(monkeypatch, tmp_path, live_server, "dev-target", "SteamDeck")

    dest_folder = tmp_path / "deck_roms" / "Pokemon Brilliant Diamond"
    runner = CliRunner()
    result = runner.invoke(pull_rom, input=f"1\n1\n{dest_folder}\n")

    assert result.exit_code == 0, result.output
    assert "pulled from SourcePC" in result.output

    pending = source.list_pending_pull_requests()
    assert len(pending) == 1
    assert pending[0]["kind"] == "rom-folder"

    # Simulate the source's sync-daemon fulfilling the pull request.
    ok = _handle_pull_request(
        source, pending[0]["id"], pending[0]["slug"], pending[0]["to_device_id"],
        pending[0]["destination_path"], pending[0]["game_name"], kind=pending[0]["kind"],
    )
    assert ok

    target = _device_client(live_server, "dev-target", "SteamDeck")
    transfers = target.list_pending_transfers()
    assert len(transfers) == 1
    assert transfers[0]["kind"] == "rom-folder"

    ok = _receive_transfer(
        target, transfers[0]["id"], transfers[0]["destination_path"],
        transfers[0]["slug"], transfers[0].get("console", ""), transfers[0]["game_name"],
        sha256=transfers[0].get("sha256"), kind=transfers[0]["kind"],
    )
    assert ok

    assert (dest_folder / "pbd.nsp").read_bytes() == b"BASEROMDATA"
    assert (dest_folder / "pbd_update.nsp").read_bytes() == b"UPDATEDATA"


def test_push_rom_no_games_configured_exits_quietly(monkeypatch, tmp_path, live_server):
    """No local ROM-configured games → the wizard reports that and returns,
    without prompting for anything (regression guard for the early-return path)."""
    _device_client(live_server, "dev-empty", "EmptyPC").list_devices()
    _write_cfg(monkeypatch, tmp_path, live_server, "dev-empty", "EmptyPC")

    runner = CliRunner()
    result = runner.invoke(push_rom, input="")

    assert result.exit_code == 0, result.output
    assert "No games with a ROM path configured" in result.output
