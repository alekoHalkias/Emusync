"""Manifest blob format (#739): codec, verification, and the sync paths that use it.

Real files, real SQLite, a real live server; no mocks."""
from __future__ import annotations

import hashlib
import io
import os
import tarfile
from types import SimpleNamespace

import pytest

from server.blob_tree import (
    blob_kind, content_hash, extract_tree, legacy_to_tree, local_manifest, manifest_size, pack_tree, verify_blob,
)
from server.sync_client import CardFormatMismatch, SyncClient, _write_memcard, _write_memcard_tar_bytes
from tests.conftest import AUTH, tree, tree_dir


def _card(root):
    (root / "GAME1").mkdir(parents=True)
    (root / "GAME1" / "GAME1").write_bytes(b"save1")
    (root / "GAME1" / "icon.sys").write_bytes(b"icon")
    (root / "_pcsx2_superblock").write_bytes(b"top")
    return root


def _files(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


# ── codec ────────────────────────────────────────────────────────────────────

def test_file_round_trip_and_hash_is_plain_sha256(tmp_path):
    f = tmp_path / "game.srm"
    f.write_bytes(b"\x00SRAM")
    blob = pack_tree(f)
    kind, tmp = extract_tree(blob, tmp_path / "out")
    assert kind == "file" and (tmp / ".emusync-file").read_bytes() == b"\x00SRAM"
    # GUI files:getFileHash hashes the plain file; the blob hash must equal it.
    assert content_hash(f) == verify_blob(blob)[1] == hashlib.sha256(b"\x00SRAM").hexdigest()


def test_file_hash_and_bytes_ignore_the_filename(tmp_path):
    a, b = tmp_path / "a.srm", tmp_path / "b.sav"
    a.write_bytes(b"same")
    b.write_bytes(b"same")
    assert pack_tree(a) == pack_tree(b) and content_hash(a) == content_hash(b)


def test_dir_round_trip_keeps_nested_layout(tmp_path):
    card = _card(tmp_path / "Mcd001.ps2")
    kind, tmp = extract_tree(pack_tree(card), tmp_path / "out")
    assert kind == "dir" and _files(tmp) == _files(card)
    assert content_hash(tmp) == content_hash(card)


def test_pack_is_deterministic_across_mtimes(tmp_path):
    card = _card(tmp_path / "card")
    first = pack_tree(card)
    os.utime(card / "GAME1" / "GAME1", (1, 1))
    assert pack_tree(card) == first


def test_bak_files_and_include_filter(tmp_path):
    d = tmp_path / "sstates"
    d.mkdir()
    for name in ("SLUS-1.p2s", "SLUS-1.p2s.bak", "SCES-2.p2s"):
        (d / name).write_bytes(name.encode())
    assert [e["path"] for e in local_manifest(d)["files"]] == ["SCES-2.p2s", "SLUS-1.p2s"]
    only = local_manifest(d, lambda rel: rel.startswith("SLUS"))
    assert [e["path"] for e in only["files"]] == ["SLUS-1.p2s"]


def test_empty_folder_round_trips(tmp_path):
    (tmp_path / "empty").mkdir()
    blob = pack_tree(tmp_path / "empty")
    assert blob_kind(blob) == "dir" and manifest_size(verify_blob(blob)[0]) == 0


# ── verification and hostile input ───────────────────────────────────────────

def _retar(blob: bytes, edit) -> bytes:
    """Rebuild *blob*'s tar with ``edit(members)`` applied: list of (TarInfo, bytes)."""
    with tarfile.open(fileobj=io.BytesIO(blob[5:])) as tar:
        members = [(m, tar.extractfile(m).read()) for m in tar.getmembers()]
    members = edit(members)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for info, data in members:
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return blob[:5] + buf.getvalue()


@pytest.mark.parametrize("edit", [
    pytest.param(lambda ms: [ms[0], (ms[1][0], b"tampered")] + ms[2:], id="changed-member"),
    pytest.param(lambda ms: ms[:-1], id="missing-member"),
    pytest.param(lambda ms: ms + [(tarfile.TarInfo("extra"), b"x")], id="extra-member"),
    pytest.param(lambda ms: ms[1:], id="no-manifest"),
])
def test_tampered_blob_is_rejected_and_target_untouched(tmp_path, edit):
    bad = _retar(pack_tree(_card(tmp_path / "src")), edit)
    dest = tmp_path / "dest" / "card"
    dest.mkdir(parents=True)
    (dest / "keep").write_bytes(b"LOCAL")
    with pytest.raises(ValueError):
        _write_memcard(dest, bad)
    assert _files(dest) == {"keep": b"LOCAL"}
    assert not [p for p in dest.parent.iterdir() if p.name.startswith(".emusync-")]


@pytest.mark.parametrize("name", ["../evil", "/abs/evil", "a/../../evil", "./x"])
def test_unsafe_manifest_paths_are_rejected(tmp_path, name):
    with pytest.raises(ValueError):
        extract_tree(tree_dir({name: b"evil"}), tmp_path / "out")
    assert not (tmp_path / "evil").exists()


def test_unusual_but_legal_names_round_trip(tmp_path):
    d = tmp_path / "save"
    d.mkdir()
    (d / "a\\b.sav").write_bytes(b"backslash")
    (d / ".emusync-manifest.json").write_bytes(b"user file")
    kind, tmp = extract_tree(pack_tree(d), tmp_path / "out")
    assert _files(tmp) == _files(d)


@pytest.mark.asyncio
async def test_restore_of_unreadable_generation_is_409(client):
    await client.post("/games", json={"name": "Zelda"}, headers=AUTH)
    await client.post("/games/zelda/save", content=tree(b"one"), headers=AUTH)
    await client.post("/games/zelda/save", content=tree(b"two"), headers=AUTH)
    from server.api import _core
    store = _core._get_store()
    old = store.list_save_history("zelda")[-1]["id"]
    store._blob_path("saves", old).write_bytes(b"ES1\0\x00one")  # left unconverted
    r = await client.post("/games/zelda/save/restore", json={"version_id": old}, headers=AUTH)
    assert r.status_code == 409


def test_symlink_member_is_rejected(tmp_path):
    def add_link(ms):
        link = tarfile.TarInfo("GAME1/GAME1")
        link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
        return [ms[0]] + [(link, b"") if m.name == "GAME1/GAME1" else (m, d) for m, d in ms[1:]]
    with pytest.raises(ValueError):
        extract_tree(_retar(pack_tree(_card(tmp_path / "src")), add_link), tmp_path / "out")


def test_file_blob_onto_folder_card_raises_mismatch(tmp_path):
    dest = _card(tmp_path / "card")
    with pytest.raises(CardFormatMismatch):
        _write_memcard(dest, tree(b"single file"))
    assert _files(dest)["GAME1/GAME1"] == b"save1"


def test_legacy_conversion_matches_a_fresh_pack(tmp_path):
    card = _card(tmp_path / "card")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(str(card), arcname=".")
    assert legacy_to_tree(2, buf.getvalue()) == pack_tree(card)
    assert legacy_to_tree(0, b"raw") == tree(b"raw")


# ── rom-folder receive paths (cli/transfer.py) ───────────────────────────────

def test_rom_folder_manifest_and_bare_tar_both_land(tmp_path):
    src = _card(tmp_path / "Game")
    via_cli = tmp_path / "a" / "Game"
    _write_memcard(via_cli, pack_tree(src))  # CLI send: manifest blob
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:  # GUI rom:push: bare `tar -cf`
        tar.add(str(src), arcname=".")
    via_gui = tmp_path / "b" / "Game"
    _write_memcard_tar_bytes(via_gui, buf.getvalue())
    assert _files(via_cli) == _files(via_gui) == _files(src)


# ── API ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/games/zelda/save", "/games/zelda/state", "/consoles/PS2/memcard"])
async def test_folder_push_records_manifest_hash_and_content_size(client, tmp_path, path):
    await client.post("/games", json={"name": "Zelda"}, headers=AUTH)
    card = _card(tmp_path / "card")
    r = await client.post(path, content=pack_tree(card), headers=AUTH)
    assert r.status_code == 200 and r.json()["hash"] == content_hash(card)
    meta = (await client.get(f"{path}/meta" if "state" not in path else "/games/zelda/state/history",
                             headers=AUTH)).json()
    size = meta["size"] if isinstance(meta, dict) else meta[0]["size"]
    assert size == sum(len(v) for v in _files(card).values())
    assert (await client.get(path, headers=AUTH)).content == pack_tree(card)


@pytest.mark.asyncio
async def test_corrupt_upload_is_400_and_leaves_no_staged_file(client, tmp_path):
    await client.post("/games", json={"name": "Zelda"}, headers=AUTH)
    good = pack_tree(_card(tmp_path / "card"))
    i = good.rindex(b"save1")
    r = await client.post("/games/zelda/save", content=good[:i] + b"savex" + good[i + 5:], headers=AUTH)
    assert r.status_code == 400
    from server.api import _core
    assert not list((_core._get_store()._blob_dir / ".uploads").glob("*"))


# ── cross-device over a live server ──────────────────────────────────────────

def test_folder_card_syncs_between_devices_without_divergence(tmp_path, live_server):
    from cli.run_reconcile import _reconcile_save
    a = SyncClient(live_server["host"], live_server["port"], "", "dev-a", "DeviceA")
    b = SyncClient(live_server["host"], live_server["port"], "", "dev-b", "DeviceB")
    slug = a.add_game("Folder Game")["slug"]
    src = _card(tmp_path / "a" / "SAVEDATA")
    assert a.push_save(slug, str(src)) == content_hash(src)

    dest = tmp_path / "b" / "SAVEDATA"
    pulled, h = b.pull_save(slug, str(dest))
    assert pulled and h == content_hash(dest) and _files(dest) == _files(src)

    cfg = SimpleNamespace(data_dir=str(tmp_path), device_id="dev-b")
    assert _reconcile_save(b, cfg, slug, str(dest)) == h  # unchanged: no push, no conflict
    assert not (tmp_path / "save_conflicts.json").exists()
