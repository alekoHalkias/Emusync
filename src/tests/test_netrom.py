"""Unit tests for the network-ROM path/copy helpers (issue #255)."""
import os

import pytest

from cli import netrom


# ── rel-path normalization / safety ──────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("GBA/game.gba", "GBA/game.gba"),
    ("GBA\\game.gba", "GBA/game.gba"),
    ("/GBA/game.gba", "GBA/game.gba"),
    ("GBA//game.gba", "GBA/game.gba"),
    ("./GBA/game.gba", "GBA/game.gba"),
    ("", ""),
])
def test_normalize_rel_path(raw, expected):
    assert netrom.normalize_rel_path(raw) == expected


@pytest.mark.parametrize("rel,ok", [
    ("GBA/game.gba", True),
    ("game.gba", True),
    ("../game.gba", False),
    ("GBA/../../etc/passwd", False),
    ("/abs/game.gba", False),
    ("\\abs\\game.gba", False),
    ("Z:/roms/game.gba", False),
    ("", False),
])
def test_is_safe_rel_path(rel, ok):
    assert netrom.is_safe_rel_path(rel) is ok


def test_sanitize_rejects_traversal():
    with pytest.raises(ValueError):
        netrom.sanitize_rel_path("../../etc/passwd")


def test_compute_rel_path(tmp_path):
    root = str(tmp_path / "nas" / "roms")
    rom = os.path.join(root, "GBA", "game.gba")
    assert netrom.compute_rel_path(root, rom) == "GBA/game.gba"


def test_compute_rel_path_outside_root_returns_none(tmp_path):
    root = str(tmp_path / "nas" / "roms")
    outside = str(tmp_path / "elsewhere" / "game.gba")
    assert netrom.compute_rel_path(root, outside) is None


def test_join_network_roundtrips(tmp_path):
    root = str(tmp_path / "mnt" / "nas")
    rel = netrom.compute_rel_path(root, os.path.join(root, "SNES", "game.sfc"))
    assert netrom.join_network(root, rel) == os.path.join(root, "SNES", "game.sfc")


def test_join_network_rejects_unsafe():
    with pytest.raises(ValueError):
        netrom.join_network("/mnt/nas", "../escape")


# ── reachability / resolution ────────────────────────────────────────────────

def test_path_is_reachable_true_for_existing(tmp_path):
    f = tmp_path / "game.gba"
    f.write_bytes(b"rom")
    assert netrom.path_is_reachable(str(f)) is True


def test_path_is_reachable_false_for_missing(tmp_path):
    assert netrom.path_is_reachable(str(tmp_path / "nope.gba")) is False


def test_resolve_local_source_returns_rom_path():
    assert netrom.resolve_rom_path("local", "/games/x.gba", "") == "/games/x.gba"


def test_resolve_network_prefers_live_master(tmp_path):
    master = tmp_path / "x.gba"
    master.write_bytes(b"rom")
    assert netrom.resolve_rom_path("network", str(master), "") == str(master)


def test_resolve_network_falls_back_to_local(tmp_path):
    missing_master = str(tmp_path / "nas" / "x.gba")  # unreachable
    local = tmp_path / "local" / "x.gba"
    local.parent.mkdir()
    local.write_bytes(b"rom")
    assert netrom.resolve_rom_path("network", missing_master, str(local)) == str(local)


def test_resolve_network_none_when_nothing_available(tmp_path):
    assert netrom.resolve_rom_path("network", str(tmp_path / "x.gba"), "") is None


# ── localize / delocalize ────────────────────────────────────────────────────

def test_localize_copies_and_returns_hash(tmp_path):
    master = tmp_path / "nas" / "x.gba"
    master.parent.mkdir()
    master.write_bytes(b"hello rom")
    dest = tmp_path / "local" / "x.gba"
    h = netrom.localize_rom(str(master), str(dest))
    assert dest.read_bytes() == b"hello rom"
    assert h == netrom.sha256_file(str(master))
    assert not (tmp_path / "local" / "x.gba.part").exists()


def test_localize_refuses_master_destination(tmp_path):
    master = tmp_path / "x.gba"
    master.write_bytes(b"rom")
    with pytest.raises(netrom.LocalizeError):
        netrom.localize_rom(str(master), str(master))


def test_localize_unreachable_master(tmp_path):
    with pytest.raises(netrom.LocalizeError):
        netrom.localize_rom(str(tmp_path / "missing.gba"), str(tmp_path / "d.gba"))


def test_delocalize_removes_local_copy(tmp_path):
    master = tmp_path / "nas" / "x.gba"
    master.parent.mkdir()
    master.write_bytes(b"rom")
    local = tmp_path / "local" / "x.gba"
    local.parent.mkdir()
    local.write_bytes(b"rom")
    assert netrom.delocalize_rom(str(local), str(master)) is True
    assert not local.exists()
    assert master.exists()  # master untouched


def test_delocalize_refuses_to_delete_master(tmp_path):
    master = tmp_path / "x.gba"
    master.write_bytes(b"rom")
    with pytest.raises(netrom.LocalizeError):
        netrom.delocalize_rom(str(master), str(master))


def test_delocalize_missing_is_noop(tmp_path):
    assert netrom.delocalize_rom(str(tmp_path / "nope.gba"), "") is False


# ── upload_to_master (issue #270) ────────────────────────────────────────────

def test_upload_copies_local_to_network_and_returns_hash(tmp_path):
    local = tmp_path / "local" / "x.gba"
    local.parent.mkdir()
    local.write_bytes(b"hello rom")
    master = tmp_path / "nas" / "GBA" / "x.gba"  # parents created by the helper
    res = netrom.upload_to_master(str(local), str(master))
    assert master.read_bytes() == b"hello rom"
    assert res.skipped is False
    assert res.sha256 == netrom.sha256_file(str(local))
    assert not (tmp_path / "nas" / "GBA" / "x.gba.part").exists()


def test_upload_skips_when_master_exists(tmp_path):
    local = tmp_path / "local" / "x.gba"
    local.parent.mkdir()
    local.write_bytes(b"new local bytes")
    master = tmp_path / "nas" / "x.gba"
    master.parent.mkdir()
    master.write_bytes(b"existing master")
    res = netrom.upload_to_master(str(local), str(master))
    assert res.skipped is True
    # Master is left untouched, and its hash (not the local one) is returned.
    assert master.read_bytes() == b"existing master"
    assert res.sha256 == netrom.sha256_file(str(master))


def test_upload_can_overwrite_when_skip_disabled(tmp_path):
    local = tmp_path / "local" / "x.gba"
    local.parent.mkdir()
    local.write_bytes(b"new local bytes")
    master = tmp_path / "nas" / "x.gba"
    master.parent.mkdir()
    master.write_bytes(b"old")
    res = netrom.upload_to_master(str(local), str(master), skip_if_exists=False)
    assert res.skipped is False
    assert master.read_bytes() == b"new local bytes"


def test_upload_refuses_same_path(tmp_path):
    f = tmp_path / "x.gba"
    f.write_bytes(b"rom")
    with pytest.raises(netrom.LocalizeError):
        netrom.upload_to_master(str(f), str(f))


def test_upload_missing_local_source(tmp_path):
    with pytest.raises(netrom.LocalizeError):
        netrom.upload_to_master(str(tmp_path / "nope.gba"), str(tmp_path / "nas" / "x.gba"))
