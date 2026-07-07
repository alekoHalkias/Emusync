"""GET/PUT /settings/steamgriddb-key (issue #322)."""
from __future__ import annotations

import pytest

from tests.conftest import AUTH


@pytest.mark.asyncio
async def test_get_steamgriddb_key_defaults_to_none(client):
    r = await client.get("/settings/steamgriddb-key", headers=AUTH)
    assert r.status_code == 200
    assert r.json() == {"api_key": None}


@pytest.mark.asyncio
async def test_set_then_get_steamgriddb_key_roundtrips(client):
    r = await client.put("/settings/steamgriddb-key", json={"api_key": "sgdb-test-key"}, headers=AUTH)
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    r = await client.get("/settings/steamgriddb-key", headers=AUTH)
    assert r.json() == {"api_key": "sgdb-test-key"}


@pytest.mark.asyncio
async def test_get_steamgriddb_key_requires_auth(client):
    r = await client.get("/settings/steamgriddb-key")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_set_steamgriddb_key_requires_auth(client):
    r = await client.put("/settings/steamgriddb-key", json={"api_key": "x"})
    assert r.status_code == 401
