"""Tests for server logging (issue #209):

1. The stdout timestamp wrapper (`_TimestampedStream`) — pure unit tests.
2. The new activity lines emitted by the API (game run/stop, save/state/ROM
   push/pull) — driven through the real app, asserting on captured stdout.
"""
from __future__ import annotations

import io
import re

import pytest

import server.config as cfg_module
from cli.server import _auto_initialize_server, _RotatingLogWriter, _TimestampedStream
from tests.conftest import MASTER_PIN

AUTH = {
    "Authorization": f"Bearer {MASTER_PIN}",
    "X-Device-ID": "device-abc",
    "X-Device-Name": "steamdeck",
}

_TS_RE = re.compile(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] ")


# ── timestamp wrapper ────────────────────────────────────────────────────────────

def test_timestamped_stream_prefixes_each_line():
    buf = io.StringIO()
    stream = _TimestampedStream(buf)
    print("hello", file=stream)
    print("world", file=stream)
    lines = buf.getvalue().splitlines()
    assert len(lines) == 2
    assert all(_TS_RE.match(ln) for ln in lines)
    assert lines[0].endswith("hello")
    assert lines[1].endswith("world")


def test_timestamped_stream_one_prefix_for_a_multiline_write():
    buf = io.StringIO()
    stream = _TimestampedStream(buf)
    stream.write("a\nb\n")
    lines = buf.getvalue().splitlines()
    assert [ln.split("] ", 1)[1] for ln in lines] == ["a", "b"]
    # Each line is stamped exactly once (no stamp injected after the trailing \n).
    assert buf.getvalue().count("[") == 2


def test_timestamped_stream_ignores_empty_write():
    buf = io.StringIO()
    stream = _TimestampedStream(buf)
    stream.write("")
    assert buf.getvalue() == ""


def test_timestamped_stream_delegates_unknown_attrs():
    buf = io.StringIO()
    stream = _TimestampedStream(buf)
    # `getvalue` isn't defined on the wrapper — it must delegate to the inner stream.
    stream.write("hi\n")
    assert "hi" in stream.getvalue()


# ── rotating log file (issue #268) ──────────────────────────────────────────────

def test_rotating_log_writer_appends_and_creates_parent(tmp_path):
    log_path = tmp_path / "sub" / "server.log"
    writer = _RotatingLogWriter(log_path)
    writer.write("line one\n")
    writer.write("line two\n")
    writer.close()
    assert log_path.read_text() == "line one\nline two\n"


def test_rotating_log_writer_rotates_when_over_cap(tmp_path):
    log_path = tmp_path / "server.log"
    # Small cap so a couple of writes trigger rotation.
    writer = _RotatingLogWriter(log_path, max_bytes=20, backups=2)
    writer.write("a" * 15 + "\n")  # 16 bytes — fits
    writer.write("b" * 15 + "\n")  # would exceed 20 → rotate first
    writer.close()
    backup = log_path.with_name("server.log.1")
    assert backup.exists()
    assert backup.read_text().startswith("a")
    assert log_path.read_text().startswith("b")


def test_rotating_log_writer_drops_oldest_backup(tmp_path):
    log_path = tmp_path / "server.log"
    writer = _RotatingLogWriter(log_path, max_bytes=20, backups=2)
    for ch in ("a", "b", "c", "d"):
        writer.write(ch * 15 + "\n")
    writer.close()
    # Only `backups` numbered files are kept (no .3).
    assert log_path.exists()
    assert log_path.with_name("server.log.1").exists()
    assert log_path.with_name("server.log.2").exists()
    assert not log_path.with_name("server.log.3").exists()


def test_timestamped_stream_mirrors_to_log_writer(tmp_path):
    log_path = tmp_path / "server.log"
    writer = _RotatingLogWriter(log_path)
    buf = io.StringIO()
    stream = _TimestampedStream(buf, log_writer=writer)
    print("mirrored", file=stream)
    writer.close()
    # The file gets the same stamped line that went to stdout.
    assert buf.getvalue() == log_path.read_text()
    assert _TS_RE.match(log_path.read_text())
    assert "mirrored" in log_path.read_text()


# ── zero-config auto-init (issue #268) ──────────────────────────────────────────

def test_auto_initialize_sets_server_flag_with_preset_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg_module, "CONFIG_PATH", tmp_path / "emusync.toml")
    cfg = cfg_module.Config()
    assert cfg.is_server is False

    out = _auto_initialize_server(cfg)

    # is_server flipped on, defaults preserved (port 8765, blank PIN = open access).
    assert out.is_server is True
    assert out.server_port == 8765
    assert out.server_pin == ""
    # Persisted to disk so the GUI auto-start path (is_server check) sees it.
    saved = cfg_module.load()
    assert saved.is_server is True


# ── activity lines ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_lock_acquire_release_log_run_and_stop(client, capsys):
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=AUTH)

    await client.post("/games/pokemon-emerald/lock", headers=AUTH)
    out = capsys.readouterr().out
    assert "Pokemon Emerald is running on steamdeck" in out

    await client.delete("/games/pokemon-emerald/lock", headers=AUTH)
    out = capsys.readouterr().out
    assert "Pokemon Emerald stopped on steamdeck" in out


@pytest.mark.asyncio
async def test_save_push_and_pull_are_logged(client, capsys):
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=AUTH)

    await client.post("/games/pokemon-emerald/save", content=b"DATA", headers=AUTH)
    assert "save pushed: Pokemon Emerald from steamdeck" in capsys.readouterr().out

    await client.get("/games/pokemon-emerald/save", headers=AUTH)
    assert "save pulled: Pokemon Emerald by steamdeck" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_state_push_and_pull_are_logged(client, capsys):
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=AUTH)

    await client.post("/games/pokemon-emerald/state", content=b"STATE", headers=AUTH)
    assert "state pushed: Pokemon Emerald from steamdeck" in capsys.readouterr().out

    await client.get("/games/pokemon-emerald/state", headers=AUTH)
    assert "state pulled: Pokemon Emerald by steamdeck" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_empty_pull_is_not_logged(client, capsys):
    # No save stored yet → 204, and nothing logged.
    await client.post("/games", json={"name": "Pokemon Emerald"}, headers=AUTH)
    capsys.readouterr()  # drain the "new device paired" / add-game noise
    r = await client.get("/games/pokemon-emerald/save", headers=AUTH)
    assert r.status_code == 204
    assert "save pulled" not in capsys.readouterr().out
