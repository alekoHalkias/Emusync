"""Folder-based PCSX2 memcard packing/writing (server/sync_client.py).

Regression coverage for a crash + a silent data-loss bug found while
debugging `emusync run` against a real PCSX2 folder memcard (issue #316/#319
follow-up): PCSX2 nests each game's saves one level down in its own
subfolder (e.g. ``GAME1/GAME1``, ``GAME1/icon.sys``), which the original
top-level-only pack/write logic didn't handle.
"""
from __future__ import annotations

import io
import tarfile
from pathlib import Path

from server.sync_client import _write_memcard, memcard_bytes


def _make_folder_card(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "_pcsx2_superblock").write_text("topfile")
    game_dir = root / "GAME1"
    game_dir.mkdir()
    (game_dir / "GAME1").write_text("save1")
    (game_dir / "icon.sys").write_text("icon")


def test_memcard_bytes_includes_nested_game_subfolders(tmp_path):
    """Previously only iterdir()'d the top level, silently dropping every
    per-game subfolder — a push would send just the loose superblock file."""
    card = tmp_path / "Mcd001.ps2"
    _make_folder_card(card)

    data = memcard_bytes(card)

    names = {m.name for m in tarfile.open(fileobj=io.BytesIO(data)).getmembers()}
    assert names == {"_pcsx2_superblock", "GAME1/GAME1", "GAME1/icon.sys"}


def test_memcard_bytes_is_deterministic_for_unchanged_content(tmp_path):
    """Required for _reconcile_save's hash comparison to treat an unchanged
    card as unchanged instead of pushing a new generation every launch."""
    card = tmp_path / "Mcd001.ps2"
    _make_folder_card(card)

    assert memcard_bytes(card) == memcard_bytes(card)


def test_write_memcard_backs_up_whole_folder_and_extracts(tmp_path):
    """On pull, the entire existing memcard folder is copied to <name>.bak
    before the new content is extracted — not individual files inside it."""
    src = tmp_path / "src"
    _make_folder_card(src)
    data = memcard_bytes(src)

    dest = tmp_path / "dest" / "Mcd001.ps2"
    (dest / "GAME1").mkdir(parents=True)
    (dest / "GAME1" / "GAME1").write_text("old-save")

    _write_memcard(dest, data)

    # New content extracted correctly
    assert (dest / "GAME1" / "GAME1").read_text() == "save1"
    assert (dest / "GAME1" / "icon.sys").read_text() == "icon"
    assert (dest / "_pcsx2_superblock").read_text() == "topfile"

    # Backup is the whole folder, not per-file .bak suffixes inside
    bak = dest.parent / (dest.name + ".bak")
    assert bak.is_dir()
    assert (bak / "GAME1" / "GAME1").read_text() == "old-save"
    assert not (dest / "GAME1" / "GAME1.bak").exists()


def _make_gci_folder_card(root: Path) -> None:
    """Dolphin's 'GCI Folder' format (its default): a folder per region/slot
    containing one subfolder per game, each with its own .gci file(s) — one
    level deeper than PCSX2's layout (#426)."""
    root.mkdir(parents=True, exist_ok=True)
    game_dir = root / "USA" / "Card A" / "GALE01"
    game_dir.mkdir(parents=True)
    (game_dir / "01-GALE-ZeldaWW.gci").write_bytes(b"gci-save-1")
    (game_dir / "01-GALE-ZeldaWW.gci.bnr").write_bytes(b"banner")


def test_memcard_bytes_includes_nested_gci_folder_saves(tmp_path):
    """Dolphin's GCI-folder format nests two levels deep (region/slot/game),
    not one like PCSX2 — confirm rglob still finds it (#426)."""
    card = tmp_path / "GC"
    _make_gci_folder_card(card)

    data = memcard_bytes(card)

    names = {m.name for m in tarfile.open(fileobj=io.BytesIO(data)).getmembers()}
    assert names == {
        "USA/Card A/GALE01/01-GALE-ZeldaWW.gci",
        "USA/Card A/GALE01/01-GALE-ZeldaWW.gci.bnr",
    }


def test_write_memcard_gci_folder_round_trips_and_backs_up_whole_tree(tmp_path):
    """Pull side must extract the nested GCI-folder tree intact and back up
    the whole existing card, not per-file (#426)."""
    src = tmp_path / "src"
    _make_gci_folder_card(src)
    data = memcard_bytes(src)

    dest = tmp_path / "dest" / "GC"
    old_game_dir = dest / "USA" / "Card A" / "GALE01"
    old_game_dir.mkdir(parents=True)
    (old_game_dir / "01-GALE-ZeldaWW.gci").write_bytes(b"old-gci-save")

    _write_memcard(dest, data)

    new_game_dir = dest / "USA" / "Card A" / "GALE01"
    assert (new_game_dir / "01-GALE-ZeldaWW.gci").read_bytes() == b"gci-save-1"
    assert (new_game_dir / "01-GALE-ZeldaWW.gci.bnr").read_bytes() == b"banner"

    bak = dest.parent / (dest.name + ".bak")
    assert bak.is_dir()
    assert (bak / "USA" / "Card A" / "GALE01" / "01-GALE-ZeldaWW.gci").read_bytes() == b"old-gci-save"


def test_write_memcard_legacy_raw_file_fallback(tmp_path):
    """A file-based memcard (non-tar bytes) still writes as a plain file."""
    dest = tmp_path / "Mcd001.ps2"
    _write_memcard(dest, b"RAWCARDBYTES")
    assert dest.read_bytes() == b"RAWCARDBYTES"


def test_write_memcard_legacy_fallback_does_not_crash_on_directory_target(tmp_path):
    """A device already using folder-based memcards receiving a raw (non-tar)
    blob from an old flat-file device must not crash trying to overwrite a
    directory as if it were a file."""
    dest = tmp_path / "Mcd001.ps2"
    (dest / "GAME1").mkdir(parents=True)

    _write_memcard(dest, b"NOT-A-TAR-ARCHIVE")  # must not raise

    assert dest.is_dir()
