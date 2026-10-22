"""Tests for the conflict-check endpoints (issue #579).

Covers the divergence logic:
- No baseline → not diverged
- Local only changed → not diverged
- Server only changed → not diverged
- Both changed, different hashes → diverged
- Both changed, same hash → not diverged (identical content)
"""
import hashlib

import pytest

from tests.conftest import AUTH, _device_auth


# ── helpers ────────────────────────────────────────────────────────────────────

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ── tests: /games/{slug}/conflicts/check ───────────────────────────────────────

@pytest.mark.asyncio
async def test_no_baseline_not_diverged(client):
    """When there's no server save, divergence is false."""
    await client.post("/games", json={"name": "Test Game", "slug": "test-game"}, headers=AUTH)
    local_hash = _sha256(b"local content")
    resp = await client.get(
        f"/games/test-game/conflicts/check", params={"local_hash": local_hash}, headers=AUTH
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["diverged"] is False


@pytest.mark.asyncio
async def test_local_only_changed_not_diverged(client):
    """Only local changed since baseline → not diverged (push is safe).

    Push from device-1 (sets baseline). Then send a different local_hash
    but the server still holds the baseline hash → server didn't change.
    """
    await client.post("/games", json={"name": "Test Game", "slug": "test-game"}, headers=AUTH)
    # Device-1 pushes save v1
    save_v1 = b"save version 1"
    await client.post("/games/test-game/save", content=save_v1, headers=AUTH)
    baseline_hash = _sha256(save_v1)
    # Client sends a different local hash (local changed, server = baseline)
    local_hash = _sha256(b"local modified")
    resp = await client.get(
        f"/games/test-game/conflicts/check", params={"local_hash": local_hash}, headers=AUTH
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["diverged"] is False


@pytest.mark.asyncio
async def test_server_only_changed_not_diverged(client):
    """Only server changed since baseline → not diverged (pull is safe).

    Push from device-1 (sets baseline). Then push from device-2 (changes server
    hash). Now send device-1's original local hash — server changed but local
    hasn't moved past baseline.
    """
    await client.post("/games", json={"name": "Test Game", "slug": "test-game"}, headers=AUTH)
    # Device-1 (test-pc) pushes save v1
    save_v1 = b"save version 1"
    await client.post("/games/test-game/save", content=save_v1, headers=AUTH)
    # Device-2 pushes save v2 (changes server hash, baseline for device-1 stays v1)
    save_v2 = b"save version 2"
    await client.post("/games/test-game/save", content=save_v2, headers=_device_auth("device-2", "other-pc"))
    # Device-1's local still holds v1 (the baseline) — check with device-1's headers
    local_hash = _sha256(save_v1)
    resp = await client.get(
        f"/games/test-game/conflicts/check", params={"local_hash": local_hash}, headers=_device_auth("device-abc", "test-pc")
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["diverged"] is False


@pytest.mark.asyncio
async def test_both_changed_different_hashes_diverged(client):
    """Both sides moved past baseline with different content → diverged."""
    await client.post("/games", json={"name": "Test Game", "slug": "test-game"}, headers=AUTH)
    # Device-1 pushes save v1 (baseline = v1)
    save_v1 = b"save version 1"
    await client.post("/games/test-game/save", content=save_v1, headers=AUTH)
    # Device-2 pushes save v2 (server hash = v2, baseline for device-1 still v1)
    save_v2 = b"save version 2"
    await client.post("/games/test-game/save", content=save_v2, headers=_device_auth("device-2", "other-pc"))
    # Device-1 now has a modified local save (v3, different from both v1 and v2)
    save_v3 = b"save version 3 - local edited"
    local_hash = _sha256(save_v3)
    resp = await client.get(
        f"/games/test-game/conflicts/check", params={"local_hash": local_hash}, headers=AUTH
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["diverged"] is True
    assert data["local_hash"] == local_hash
    assert data["server_hash"] == _sha256(save_v2)
    assert "server_pushed_at" in data
    assert "baseline_hash" in data


@pytest.mark.asyncio
async def test_both_changed_same_hash_not_diverged(client):
    """Both changed but end up with the same hash → not diverged."""
    await client.post("/games", json={"name": "Test Game", "slug": "test-game"}, headers=AUTH)
    save_v1 = b"save version 1"
    await client.post("/games/test-game/save", content=save_v1, headers=AUTH)
    save_v2 = b"save version 2"
    await client.post("/games/test-game/save", content=save_v2, headers=_device_auth("device-2", "other-pc"))
    # Device-1's local somehow matches server (v2) — identical content, no conflict
    local_hash = _sha256(save_v2)
    resp = await client.get(
        f"/games/test-game/conflicts/check", params={"local_hash": local_hash}, headers=AUTH
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["diverged"] is False


# ── tests: /games/{slug}/state/conflicts/check ─────────────────────────────────

@pytest.mark.asyncio
async def test_state_no_baseline_not_diverged(client):
    """State endpoint: no server state → not diverged."""
    await client.post("/games", json={"name": "Test Game", "slug": "test-game"}, headers=AUTH)
    local_hash = _sha256(b"local state")
    resp = await client.get(
        f"/games/test-game/state/conflicts/check", params={"local_hash": local_hash}, headers=AUTH
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["diverged"] is False


@pytest.mark.asyncio
async def test_state_both_changed_different_hashes_diverged(client):
    """State endpoint: both have states, different hashes → diverged."""
    await client.post("/games", json={"name": "Test Game", "slug": "test-game"}, headers=AUTH)
    # Push a state via the state push endpoint
    state_v1 = b"state version 1"
    await client.post("/games/test-game/state", content=state_v1, headers=AUTH)
    server_hash = _sha256(state_v1)
    # Client sends a different local state hash
    local_hash = _sha256(b"state version 2 - local edited")
    resp = await client.get(
        f"/games/test-game/state/conflicts/check", params={"local_hash": local_hash}, headers=AUTH
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["diverged"] is True
    assert data["local_hash"] == local_hash
    assert data["server_hash"] == server_hash


@pytest.mark.asyncio
async def test_state_same_hash_not_diverged(client):
    """State endpoint: same hash → not diverged."""
    await client.post("/games", json={"name": "Test Game", "slug": "test-game"}, headers=AUTH)
    state_v1 = b"state version 1"
    await client.post("/games/test-game/state", content=state_v1, headers=AUTH)
    server_hash = _sha256(state_v1)
    # Client sends the same hash
    resp = await client.get(
        f"/games/test-game/state/conflicts/check", params={"local_hash": server_hash}, headers=AUTH
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["diverged"] is False


# ── tests: missing slug / bad params ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_missing_game_returns_404(client):
    resp = await client.get(
        "/games/nonexistent/conflicts/check", params={"local_hash": "abc"}, headers=AUTH
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_missing_local_hash_param_returns_422(client):
    await client.post("/games", json={"name": "Test Game", "slug": "test-game"}, headers=AUTH)
    resp = await client.get(f"/games/test-game/conflicts/check", headers=AUTH)
    assert resp.status_code == 422
