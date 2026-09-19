"""CLI-level tests for `emusync game push-save`/`pull-save`/`push-state`/
`pull-state` and `emusync console push-memcard`/`pull-memcard` (#479) — backs
the GUI's manual push/pull buttons, which used to reimplement the transfer
logic themselves in TypeScript. Follows test_switch_pull_no_local_save.py's
pattern: drives the actual click command via CliRunner against a real
uvicorn server.
"""
from __future__ import annotations

from click.testing import CliRunner

import server.config as cfg_module
from cli.console import console_pull_memcard, console_push_memcard
from cli.game import game_pull_save, game_pull_state, game_push_save, game_push_state
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


# ── game push-save / pull-save ─────────────────────────────────────────────

def test_push_save_uploads_to_server(monkeypatch, tmp_path, live_server):
    client = _device_client(live_server, "dev-a", "DeviceA")
    client.add_game("Pokemon Emerald")
    _write_cfg(monkeypatch, tmp_path, live_server, "dev-a", "DeviceA")

    save = tmp_path / "emerald.srm"
    save.write_bytes(b"save bytes")

    runner = CliRunner()
    result = runner.invoke(game_push_save, ["pokemon-emerald", str(save)])

    assert result.exit_code == 0, result.output
    meta = client.get_save_meta("pokemon-emerald")
    assert meta is not None


def test_pull_save_writes_server_content_to_disk(monkeypatch, tmp_path, live_server):
    client_a = _device_client(live_server, "dev-a", "DeviceA")
    client_a.add_game("Pokemon Emerald")
    a_save = tmp_path / "a" / "emerald.srm"
    a_save.parent.mkdir(parents=True)
    a_save.write_bytes(b"real progress")
    client_a.push_save("pokemon-emerald", str(a_save))

    _write_cfg(monkeypatch, tmp_path, live_server, "dev-b", "DeviceB")
    b_save = tmp_path / "b" / "emerald.srm"
    b_save.parent.mkdir(parents=True)

    runner = CliRunner()
    result = runner.invoke(game_pull_save, ["pokemon-emerald", str(b_save)])

    assert result.exit_code == 0, result.output
    assert b_save.read_bytes() == b"real progress"


def test_pull_save_exits_2_when_nothing_on_server(monkeypatch, tmp_path, live_server):
    client = _device_client(live_server, "dev-a", "DeviceA")
    client.add_game("Untouched Game")
    _write_cfg(monkeypatch, tmp_path, live_server, "dev-a", "DeviceA")

    runner = CliRunner()
    result = runner.invoke(game_pull_save, ["untouched-game", str(tmp_path / "x.srm")])

    assert result.exit_code == 2, result.output


# ── game push-state / pull-state ────────────────────────────────────────────

def test_push_state_uploads_to_server(monkeypatch, tmp_path, live_server):
    client = _device_client(live_server, "dev-a", "DeviceA")
    client.add_game("Pokemon Emerald")
    _write_cfg(monkeypatch, tmp_path, live_server, "dev-a", "DeviceA")

    states = tmp_path / "states"
    states.mkdir()
    (states / "game.state").write_bytes(b"state bytes")

    runner = CliRunner()
    result = runner.invoke(game_push_state, ["pokemon-emerald", str(states)])

    assert result.exit_code == 0, result.output
    assert client.get_save_meta("pokemon-emerald") is None  # states are separate from saves


def test_pull_state_writes_server_content_to_disk(monkeypatch, tmp_path, live_server):
    client_a = _device_client(live_server, "dev-a", "DeviceA")
    client_a.add_game("Pokemon Emerald")
    a_states = tmp_path / "a_states"
    a_states.mkdir()
    (a_states / "game.state").write_bytes(b"real state progress")
    client_a.push_state("pokemon-emerald", str(a_states))

    _write_cfg(monkeypatch, tmp_path, live_server, "dev-b", "DeviceB")
    b_states = tmp_path / "b_states"

    runner = CliRunner()
    result = runner.invoke(game_pull_state, ["pokemon-emerald", str(b_states)])

    assert result.exit_code == 0, result.output
    assert (b_states / "game.state").read_bytes() == b"real state progress"


def test_pull_state_exits_2_when_nothing_on_server(monkeypatch, tmp_path, live_server):
    client = _device_client(live_server, "dev-a", "DeviceA")
    client.add_game("Untouched Game")
    _write_cfg(monkeypatch, tmp_path, live_server, "dev-a", "DeviceA")

    runner = CliRunner()
    result = runner.invoke(game_pull_state, ["untouched-game", str(tmp_path / "states")])

    assert result.exit_code == 2, result.output


# ── console push-memcard / pull-memcard ─────────────────────────────────────

def test_push_memcard_uploads_to_server(monkeypatch, tmp_path, live_server):
    _write_cfg(monkeypatch, tmp_path, live_server, "dev-a", "DeviceA")
    client = _device_client(live_server, "dev-a", "DeviceA")

    card = tmp_path / "Mcd001.ps2"
    card.write_bytes(b"card bytes")

    runner = CliRunner()
    result = runner.invoke(console_push_memcard, ["PS2", str(card)])

    assert result.exit_code == 0, result.output
    assert client.get_console_memcard_meta("PS2") is not None


def test_pull_memcard_writes_server_content_to_disk(monkeypatch, tmp_path, live_server):
    client_a = _device_client(live_server, "dev-a", "DeviceA")
    a_card = tmp_path / "a" / "Mcd001.ps2"
    a_card.parent.mkdir(parents=True)
    a_card.write_bytes(b"real card data")
    client_a.push_console_memcard("PS2", str(a_card))

    _write_cfg(monkeypatch, tmp_path, live_server, "dev-b", "DeviceB")
    b_card = tmp_path / "b" / "Mcd001.ps2"
    b_card.parent.mkdir(parents=True)

    runner = CliRunner()
    result = runner.invoke(console_pull_memcard, ["PS2", str(b_card)])

    assert result.exit_code == 0, result.output
    assert b_card.read_bytes() == b"real card data"


def test_pull_memcard_exits_2_when_nothing_on_server(monkeypatch, tmp_path, live_server):
    _write_cfg(monkeypatch, tmp_path, live_server, "dev-a", "DeviceA")

    runner = CliRunner()
    result = runner.invoke(console_pull_memcard, ["DC", str(tmp_path / "vmu.bin")])

    assert result.exit_code == 2, result.output
