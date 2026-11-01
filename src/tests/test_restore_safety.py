"""Hardening + restore safety regressions (issue #692)."""
from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from tests.conftest import AUTH
from server.sync_client import (
    _FMT_TARGZ,
    _extract_state_folder,
    _merge_extract_state_folder,
    _pack_envelope,
    _write_memcard_tar_bytes,
)


def _targz(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _no_temp(parent: Path) -> bool:
    return not [p for p in parent.iterdir() if p.name.startswith(".emusync-")]


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", ["null", "http://localhost:5173", "http://127.0.0.1:8765"])
async def test_cors_allows_electron_and_local_origins(client, origin):
    r = await client.options("/health", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") == origin


@pytest.mark.asyncio
async def test_cors_rejects_foreign_origin(client):
    r = await client.options("/health", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in r.headers


@pytest.mark.asyncio
async def test_pin_check(client):
    assert (await client.get("/games", headers=AUTH)).status_code == 200
    bad = {**AUTH, "Authorization": "Bearer wrong"}
    assert (await client.get("/games", headers=bad)).status_code == 401
    odd = {**AUTH, "Authorization": "Bearer p\u00e9".encode("latin-1")}
    assert (await client.get("/games", headers=odd)).status_code == 401


def test_memcard_restore_failure_keeps_card(tmp_path):
    card = tmp_path / "Mcd001.ps2"
    card.mkdir()
    (card / "keep").write_text("old")
    with pytest.raises(tarfile.TarError):
        _write_memcard_tar_bytes(card, b"not a tar")
    assert (card / "keep").read_text() == "old"
    assert not (tmp_path / "Mcd001.ps2.bak").exists()
    assert _no_temp(tmp_path)


def test_memcard_restore_replaces_file_card_and_backs_up(tmp_path):
    card = tmp_path / "card"
    card.write_text("old")
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w") as tar:
        info = tarfile.TarInfo("sub/x")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"n"))
    _write_memcard_tar_bytes(card, data.getvalue())
    assert (card / "sub" / "x").read_text() == "n"
    assert (tmp_path / "card.bak").read_text() == "old"
    assert _no_temp(tmp_path)


def test_state_extract_failure_leaves_files(tmp_path):
    folder = tmp_path / "states"
    folder.mkdir()
    (folder / "a.state").write_text("old")
    with pytest.raises(tarfile.TarError):
        _extract_state_folder(_pack_envelope(_FMT_TARGZ, b"garbage"), folder)
    assert (folder / "a.state").read_text() == "old"
    assert not (folder / "a.state.bak").exists()
    assert _no_temp(tmp_path)


def test_state_extract_success_backs_up(tmp_path):
    folder = tmp_path / "states"
    folder.mkdir()
    (folder / "a.state").write_text("old")
    _extract_state_folder(_pack_envelope(_FMT_TARGZ, _targz({"a.state": b"new"})), folder)
    assert (folder / "a.state").read_text() == "new"
    assert (folder / "a.state.bak").read_text() == "old"
    assert _no_temp(tmp_path)


def test_state_extract_legacy_raw_blob(tmp_path):
    folder = tmp_path / "Game"
    _extract_state_folder(b"RAWSTATE", folder)
    assert (folder / "Game.state").read_bytes() == b"RAWSTATE"


def test_merge_backs_up_subfolder_member(tmp_path):
    folder = tmp_path / "sstates"
    (folder / "sub").mkdir(parents=True)
    (folder / "sub" / "a.state").write_text("old")
    (folder / "other.state").write_text("other")
    _merge_extract_state_folder(_pack_envelope(_FMT_TARGZ, _targz({"sub/a.state": b"new"})), folder)
    assert (folder / "sub" / "a.state").read_text() == "new"
    assert (folder / "sub" / "a.state.bak").read_text() == "old"
    assert (folder / "other.state").read_text() == "other"
    assert _no_temp(tmp_path)


def test_merge_traversal_rejected_without_backup(tmp_path):
    folder = tmp_path / "sstates"
    folder.mkdir()
    (folder / "x").write_text("keep")
    with pytest.raises(tarfile.TarError):
        _merge_extract_state_folder(_pack_envelope(_FMT_TARGZ, _targz({"../x": b"evil"})), folder)
    assert (folder / "x").read_text() == "keep"
    assert not (folder / "x.bak").exists()
    assert not (tmp_path / "x").exists()
