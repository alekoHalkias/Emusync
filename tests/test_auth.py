"""Health, authentication, and blank-PIN (open access) tests."""
from __future__ import annotations

import pytest

from tests.conftest import AUTH, DEVICE_ID, DEVICE_NAME, MASTER_PIN, _device_auth


# ── health ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ── authentication ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_auth_required(client):
    """Requests without headers should be rejected."""
    r = await client.get("/games")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_wrong_pin_rejected(client):
    """Wrong PIN should be rejected with 401."""
    bad_auth = _device_auth(DEVICE_ID, DEVICE_NAME, pin="wrong")
    r = await client.get("/games", headers=bad_auth)
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_missing_device_id_rejected(client):
    """Missing X-Device-ID header should be rejected."""
    r = await client.get("/games", headers={"Authorization": f"Bearer {MASTER_PIN}"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_device_auto_registered_on_first_request(client):
    """Devices should be auto-registered on first authenticated request — no explicit pair step."""
    r = await client.get("/games", headers=AUTH)
    assert r.status_code == 200

    r = await client.get("/devices", headers=AUTH)
    devices = r.json()
    assert any(d["id"] == DEVICE_ID for d in devices)
    assert any(d["name"] == DEVICE_NAME for d in devices)


# ── blank PIN (open access) ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_blank_pin_server_allows_any_device(make_client):
    """When server_pin is blank, any device connects without a code."""
    c = await make_client(pin="")  # blank = open access
    r = await c.get("/games", headers={"Authorization": "Bearer ", "X-Device-ID": "open-device", "X-Device-Name": "Open"})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_blank_pin_server_ignores_wrong_pin(make_client):
    """Blank server PIN accepts requests even with a non-empty PIN value."""
    c = await make_client(pin="")
    r = await c.get("/games", headers={"Authorization": "Bearer wrong-pin", "X-Device-ID": "d1", "X-Device-Name": "D1"})
    assert r.status_code == 200
