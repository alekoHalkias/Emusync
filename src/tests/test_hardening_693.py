"""#693: upload cleanup/cap, mod path validation, header sanitization."""
from __future__ import annotations

import pytest

from server.api import _core, transfers
from tests.conftest import AUTH, _device_auth


@pytest.mark.asyncio
async def test_upload_over_cap_leaves_no_staging(make_client, tmp_path, monkeypatch):
    c = await make_client(data_dir=str(tmp_path))
    src, dst = _device_auth("dev-src", "PC"), _device_auth("dev-dst", "Deck")
    await c.get("/games", headers=src)
    await c.get("/games", headers=dst)
    await c.post("/games", json={"name": "Metroid", "console": "GBA"}, headers=src)
    hdrs = {**src, "X-To-Device-ID": "dev-dst", "X-Filename": "m.gba"}
    monkeypatch.setattr(transfers, "_MAX_UPLOAD_BYTES", 10)
    r = await c.post("/games/metroid/rom-transfer", content=b"x" * 100, headers=hdrs)
    assert r.status_code == 413
    assert list((tmp_path / "rom_staging").iterdir()) == []
    monkeypatch.setattr(transfers, "_MAX_UPLOAD_BYTES", 1000)
    r = await c.post("/games/metroid/rom-transfer", content=b"x" * 100, headers=hdrs)
    assert r.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["a%2Fb", "a%5Cb", "%00", "x%0Ay"])
async def test_mod_names_rejected(client, bad):
    ok = "0100000000010000"
    for method, url in (
        ("get", f"/switch/{ok}/mods/{bad}"),
        ("post", f"/switch/{ok}/mods/{bad}"),
        ("get", f"/switch/{bad}/mods"),
        ("post", f"/switch/{bad}/mods/m"),
    ):
        r = await getattr(client, method)(url, headers=AUTH)
        assert r.status_code in (400, 404), (method, url, r.status_code)  # encoded "/" never matches a route


@pytest.mark.asyncio
async def test_valid_mod_roundtrip(client):
    r = await client.post("/switch/0100000000010000/mods/My Mod", content=b"tar", headers=AUTH)
    assert r.status_code == 200 and r.json()["added"] is True
    r = await client.get("/switch/0100000000010000/mods", headers=AUTH)
    assert [m["mod_name"] for m in r.json()] == ["My Mod"]
    r = await client.get("/switch/0100000000010000/mods/My Mod", headers=AUTH)
    assert r.content == b"tar"


def test_safe_segment_direct():
    from fastapi import HTTPException
    for bad in ("", ".", "..", "a/b", "a\\b", "a\x00b", "a\nb", "x" * 256):
        with pytest.raises(HTTPException):
            _core._safe_segment(bad, "t")
    assert _core._safe_segment("My Mod", "t") == "My Mod"


def test_clean_header():
    assert _core._clean_header("evil\r\nfake line") == "evilfake line"
    assert _core._clean_header(None) == ""
    assert len(_core._clean_header("a" * 200)) == 64


@pytest.mark.asyncio
async def test_device_name_sanitized_and_falls_back(client):
    await client.get("/games", headers=_device_auth("dev-x", "bad\tname"))
    await client.get("/games", headers=_device_auth("dev-y", "\t"))
    names = {d["id"]: d["name"] for d in (await client.get("/devices", headers=AUTH)).json()}
    assert names["dev-x"] == "badname"
    assert names["dev-y"] == "dev-y"
