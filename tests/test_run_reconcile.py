"""Unit tests for the `emusync run` wrapper's save-reconciliation policy,
offline-play logging, and local game-device cache (issue #5).

These cover the pure decision logic and the on-disk helpers — no server needed.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from cli.run import (
    _cache_game_device,
    _decide_save_action,
    _load_cached_game_device,
    _log_offline_play,
    _parse_iso,
    _reconcile_save,
    _run_offline,
)
from server.sync_client import GameDeviceConfig

NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
EARLIER = NOW - timedelta(hours=2)
LATER = NOW + timedelta(hours=2)


def _meta(hash_: str, pushed_at: datetime) -> dict:
    return {"hash": hash_, "pushed_at": pushed_at.isoformat()}


# ── _decide_save_action ────────────────────────────────────────────────────────

def test_no_local_no_server_is_noop():
    assert _decide_save_action(None, None, None) == "noop"


def test_no_local_but_server_pulls():
    assert _decide_save_action(None, None, _meta("abc", NOW)) == "pull"


def test_local_but_no_server_pushes():
    assert _decide_save_action("abc", NOW, None) == "push"


def test_identical_hashes_noop():
    assert _decide_save_action("same", NOW, _meta("same", EARLIER)) == "noop"


def test_divergence_local_newer_pushes():
    # local changed more recently than the server's pushed_at → local wins
    assert _decide_save_action("local", LATER, _meta("server", NOW)) == "push"


def test_divergence_server_newer_pulls():
    assert _decide_save_action("local", EARLIER, _meta("server", NOW)) == "pull"


def test_divergence_unparseable_server_time_defaults_to_push():
    assert _decide_save_action("local", NOW, {"hash": "server", "pushed_at": "garbage"}) == "push"


def test_divergence_missing_local_mtime_pulls():
    # local hash present but mtime unknown → don't risk clobbering server
    assert _decide_save_action("local", None, _meta("server", NOW)) == "pull"


# ── _parse_iso ──────────────────────────────────────────────────────────────────

def test_parse_iso_handles_naive_and_aware_and_bad():
    assert _parse_iso(NOW.isoformat()) == NOW
    naive = _parse_iso("2026-06-01T12:00:00")
    assert naive is not None and naive.tzinfo is timezone.utc
    assert _parse_iso("nope") is None
    assert _parse_iso(None) is None


# ── game-device cache ───────────────────────────────────────────────────────────

def test_game_device_cache_round_trip(tmp_path):
    cfg = SimpleNamespace(data_dir=str(tmp_path))
    gd = GameDeviceConfig(
        rom_path="/roms/x.gba", save_path="/saves/x.srm",
        launch_command="ra x.gba", state_path="/states/X", rom_folder_path="/roms",
    )
    assert _load_cached_game_device(cfg, "x") is None
    _cache_game_device(cfg, "x", gd)
    loaded = _load_cached_game_device(cfg, "x")
    assert loaded is not None
    assert loaded.save_path == "/saves/x.srm"
    assert loaded.state_path == "/states/X"
    assert loaded.launch_command == "ra x.gba"


# ── offline play log ────────────────────────────────────────────────────────────

# ── conflict warning + log (#5) ─────────────────────────────────────────────────

class _FakeClient:
    """Minimal stand-in for SyncClient — records which sync action ran.
    (Not a DB mock; the project's no-mocks rule is about SQLite.)"""

    def __init__(self, meta, server_hash="server-hash"):
        self._meta = meta
        self._server_hash = server_hash
        self.pushed = False
        self.pulled = False

    def get_save_meta(self, slug):
        return self._meta

    def push_save(self, slug, path):
        self.pushed = True
        return "local-hash"

    def pull_save(self, slug, path):
        self.pulled = True
        return True, self._server_hash


def _write_save(path: Path, data: bytes, mtime: datetime) -> None:
    path.write_bytes(data)
    os.utime(path, (mtime.timestamp(), mtime.timestamp()))


def test_reconcile_local_newer_conflict_pushes_warns_and_logs(tmp_path):
    save = tmp_path / "s.srm"
    _write_save(save, b"LOCAL-NEW", NOW)  # local edited "now"
    server_meta = {"hash": "server-old", "pushed_at": EARLIER.isoformat()}
    cfg = SimpleNamespace(data_dir=str(tmp_path))
    client = _FakeClient(server_meta)

    _reconcile_save(client, cfg, "metroid", str(save))

    assert client.pushed and not client.pulled
    conflicts = json.loads((tmp_path / "save_conflicts.json").read_text())
    assert len(conflicts) == 1
    assert conflicts[0]["winner"] == "local"
    assert conflicts[0]["server_hash"] == "server-old"


def test_reconcile_server_newer_conflict_pulls_warns_and_logs(tmp_path):
    save = tmp_path / "s.srm"
    _write_save(save, b"LOCAL-OLD", EARLIER)
    server_meta = {"hash": "server-new", "pushed_at": NOW.isoformat()}
    cfg = SimpleNamespace(data_dir=str(tmp_path))
    client = _FakeClient(server_meta)

    _reconcile_save(client, cfg, "zelda", str(save))

    assert client.pulled and not client.pushed
    conflicts = json.loads((tmp_path / "save_conflicts.json").read_text())
    assert conflicts[0]["winner"] == "server"


def test_reconcile_no_conflict_logged_when_not_diverged(tmp_path):
    # Server has no save → push, but this is not a divergence, so no conflict log.
    save = tmp_path / "s.srm"
    _write_save(save, b"DATA", NOW)
    cfg = SimpleNamespace(data_dir=str(tmp_path))
    client = _FakeClient(None)

    _reconcile_save(client, cfg, "g", str(save))

    assert client.pushed
    assert not (tmp_path / "save_conflicts.json").exists()


def test_offline_play_log_appends_and_records_save(tmp_path):
    cfg = SimpleNamespace(data_dir=str(tmp_path))
    save = tmp_path / "save.srm"
    save.write_bytes(b"offline-progress")

    _log_offline_play(cfg, "metroid", NOW.isoformat(), LATER.isoformat(), str(save))
    _log_offline_play(cfg, "zelda", NOW.isoformat(), LATER.isoformat(), "")

    log = json.loads((tmp_path / "offline_plays.json").read_text())
    assert len(log) == 2
    first = log[0]
    assert first["slug"] == "metroid"
    assert first["offline"] is True
    assert first["started_at"] == NOW.isoformat()
    assert "save_hash" in first and "save_mtime" in first
    # second entry had no save file — no hash recorded, but still logged
    assert log[1]["slug"] == "zelda"
    assert "save_hash" not in log[1]


# ── offline launch derives its command from the cached config (#207) ─────────────

def test_run_offline_errors_without_cached_command(tmp_path):
    # No cached config at all → can't know how to launch, so exit non-zero.
    cfg = SimpleNamespace(data_dir=str(tmp_path))
    with pytest.raises(SystemExit) as exc:
        _run_offline(cfg, "never-played", tmp_path / ".game_pid")
    assert exc.value.code == 1


def test_run_offline_launches_using_cached_launch_command(tmp_path):
    # A game played online at least once has its launch_command cached; offline
    # launch parses it (via shlex) and runs it without any command being passed.
    cfg = SimpleNamespace(data_dir=str(tmp_path))
    save = tmp_path / "save.srm"
    save.write_bytes(b"progress")
    gd = GameDeviceConfig(
        rom_path="/roms/x.gba", save_path=str(save),
        launch_command="true", state_path="", rom_folder_path="/roms",
    )
    _cache_game_device(cfg, "x", gd)

    with pytest.raises(SystemExit) as exc:
        _run_offline(cfg, "x", tmp_path / ".game_pid")
    assert exc.value.code == 0  # `true` exits 0

    # The play was logged for later reconciliation.
    log = json.loads((tmp_path / "offline_plays.json").read_text())
    assert log[-1]["slug"] == "x"


def test_run_offline_explicit_command_overrides_cached(tmp_path):
    # Old-method fallback: an explicit command wins over the cached launch_command.
    cfg = SimpleNamespace(data_dir=str(tmp_path))
    save = tmp_path / "save.srm"
    save.write_bytes(b"progress")
    gd = GameDeviceConfig(
        rom_path="/roms/x.gba", save_path=str(save),
        launch_command="false", state_path="", rom_folder_path="/roms",  # cached cmd fails
    )
    _cache_game_device(cfg, "x", gd)

    with pytest.raises(SystemExit) as exc:
        _run_offline(cfg, "x", tmp_path / ".game_pid", command=("true",))
    assert exc.value.code == 0  # ran the override `true`, not the cached `false`


# ── old-method fallback gates on the game being imported (#207) ───────────────────

def test_run_refuses_external_command_for_unimported_game(monkeypatch, tmp_path):
    # A passed-in command for a game EmuSync doesn't know about → refuse to launch.
    import cli.run as run_mod

    cfg = SimpleNamespace(data_dir=str(tmp_path), device_id="d", device_name="pc")
    monkeypatch.setattr(run_mod.cfg_module, "load", lambda: cfg)

    class _C:
        def health(self):
            return True

        def get_game_device(self, slug):
            return None  # not imported on this device

    monkeypatch.setattr(run_mod, "_client", lambda c: _C())

    with pytest.raises(SystemExit) as exc:
        run_mod.run_game.callback(game_slug="ghost", command=("retroarch", "ghost.gba"))
    assert exc.value.code == 1
