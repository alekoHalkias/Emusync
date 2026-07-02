"""
Shared fixtures for EmuSync integration tests — real SQLite DB, real FastAPI
app, no mocks.

Run:  .venv/bin/python -m pytest tests/ -v
"""
from __future__ import annotations

import socket
import tempfile
import threading
import time

import pytest
import pytest_asyncio
import uvicorn
from httpx import ASGITransport, AsyncClient

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from server import api as api_module
from server.store import Store

MASTER_PIN = "test-master-pin"
DEVICE_ID = "device-abc"
DEVICE_NAME = "test-pc"

# Standard auth headers for the default test device
AUTH = {
    "Authorization": f"Bearer {MASTER_PIN}",
    "X-Device-ID": DEVICE_ID,
    "X-Device-Name": DEVICE_NAME,
}


def _device_auth(device_id: str, device_name: str, pin: str = MASTER_PIN) -> dict:
    """Build auth headers for a specific device."""
    return {
        "Authorization": f"Bearer {pin}",
        "X-Device-ID": device_id,
        "X-Device-Name": device_name,
    }


@pytest_asyncio.fixture
async def client():
    """Fresh in-memory store + FastAPI app for each test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        api_module.init(store, MASTER_PIN)
        async with AsyncClient(
            transport=ASGITransport(app=api_module.app),
            base_url="http://test",
        ) as c:
            yield c


@pytest_asyncio.fixture
async def make_client():
    """Factory for self-contained tests needing a custom data_dir or PIN.

    Usage:  c = await make_client(data_dir=str(tmp_path))  /  pin=""

    Each call builds a fresh Store + initialised app + AsyncClient; all are torn
    down when the test ends. Replaces the inline AsyncClient setup that the
    blank-PIN, ROM-staging, and device-deletion tests used to repeat.
    """
    from contextlib import AsyncExitStack
    stack = AsyncExitStack()
    tmpdirs: list[tempfile.TemporaryDirectory] = []

    async def _make(data_dir: str = "", pin: str = MASTER_PIN) -> AsyncClient:
        td = tempfile.TemporaryDirectory()
        tmpdirs.append(td)
        store = Store(td.name)
        api_module.init(store, pin, data_dir)
        return await stack.enter_async_context(
            AsyncClient(
                transport=ASGITransport(app=api_module.app),
                base_url="http://test",
            )
        )

    yield _make
    await stack.aclose()
    for td in tmpdirs:
        td.cleanup()


@pytest.fixture
def live_server(tmp_path):
    """Real uvicorn server on a free localhost port, backed by a fresh Store.

    CLI commands like `push`/`pull` (cli/transfer.py) build a real httpx.Client
    against host:port — there's no ASGI shortcut for that, so CLI-level tests
    need actual sockets. Blank PIN (open access) keeps device setup simple.
    """
    store = Store(str(tmp_path / "server_data"))
    api_module.init(store, "", str(tmp_path / "server_data"))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    config = uvicorn.Config(api_module.app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield {"host": "127.0.0.1", "port": port}
    server.should_exit = True
    thread.join(timeout=5)
