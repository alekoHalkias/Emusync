"""SSE reconnect must not drop the new stream's queue (#700)."""
from __future__ import annotations

import json

import pytest

from server.api import _core
from server.api.transfers import stream_events_sse


@pytest.mark.asyncio
async def test_old_stream_cleanup_keeps_new_queue(make_client):
    await make_client()
    old = await stream_events_sse("dev-a")
    new = await stream_events_sse("dev-a")
    new_q = _core._device_event_queues["dev-a"]

    # Superseded stream ends cleanly and must not unregister the new queue.
    assert [c async for c in old.body_iterator] == []
    assert _core._device_event_queues["dev-a"] is new_q

    new_q.put_nowait({"type": "rom_transfer_queued"})
    chunk = await new.body_iterator.__anext__()
    assert json.loads(chunk.removeprefix("data: ")) == {"type": "rom_transfer_queued"}

    await new.body_iterator.aclose()
    assert "dev-a" not in _core._device_event_queues
