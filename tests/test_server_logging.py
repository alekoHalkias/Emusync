"""Tests for server logging (issue #209):

1. The stdout timestamp wrapper (`_TimestampedStream`) — pure unit tests.
2. The new activity lines emitted by the API (game run/stop, save/state/ROM
   push/pull) — driven through the real app, asserting on captured stdout.
"""
from __future__ import annotations

import io
import re
import sys
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from cli.server import _TimestampedStream
from server import api as api_module
from server.store import Store

MASTER_PIN = "test-master-pin"
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


# ── activity lines ───────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        api_module.init(store, MASTER_PIN, tmpdir)
        async with AsyncClient(
            transport=ASGITransport(app=api_module.app),
            base_url="http://test",
        ) as c:
            yield c


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
