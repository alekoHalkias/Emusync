"""Tests for PS3 directory-style ROM scanning (issue #553).

Verifies that _scan_rom_dir() detects PS3 games stored as
<game>/PS3_GAME/USRDIR/EBOOT.BIN folders alongside file-style ROMs.
"""
from __future__ import annotations

from cli.consoles_data import _IMPORT_CONSOLES
from cli.detect import _dir_matches_pattern, _scan_rom_dir

_PS3_DEF = next(c for c in _IMPORT_CONSOLES if c["key"] == "ps3")


def test_dir_matches_pattern_full(tmp_path):
    """PS3_GAME/USRDIR/EBOOT.BIN pattern matches when all components exist."""
    rom_dir = tmp_path / "Game Name"
    rom_dir.mkdir()
    (rom_dir / "PS3_GAME").mkdir()
    (rom_dir / "PS3_GAME" / "USRDIR").mkdir()
    (rom_dir / "PS3_GAME" / "USRDIR" / "EBOOT.BIN").write_text("bin")
    assert _dir_matches_pattern(str(rom_dir), "PS3_GAME/USRDIR/EBOOT.BIN") is True


def test_dir_matches_pattern_missing_intermediate(tmp_path):
    """Pattern does not match when an intermediate directory is missing."""
    rom_dir = tmp_path / "Game Name"
    rom_dir.mkdir()
    (rom_dir / "PS3_GAME").mkdir()
    # USRDIR is missing
    assert _dir_matches_pattern(str(rom_dir), "PS3_GAME/USRDIR/EBOOT.BIN") is False


def test_dir_matches_pattern_eboot_is_dir(tmp_path):
    """Pattern does not match when EBOOT.BIN is a directory, not a file."""
    rom_dir = tmp_path / "Game Name"
    rom_dir.mkdir()
    ps3_game = rom_dir / "PS3_GAME"
    ps3_game.mkdir()
    usrd = ps3_game / "USRDIR"
    usrd.mkdir()
    (usrd / "EBOOT.BIN").mkdir()  # directory, not file
    assert _dir_matches_pattern(str(rom_dir), "PS3_GAME/USRDIR/EBOOT.BIN") is False


def test_scan_rom_dir_detects_ps3_dir_rom(tmp_path):
    """Directory ROM pattern yields parent directory as ROM entry."""
    rom_root = tmp_path / "roms"
    rom_root.mkdir()
    game_dir = rom_root / "My PS3 Game"
    game_dir.mkdir()
    (game_dir / "PS3_GAME").mkdir()
    (game_dir / "PS3_GAME" / "USRDIR").mkdir()
    (game_dir / "PS3_GAME" / "USRDIR" / "EBOOT.BIN").write_text("bin")

    roms = _scan_rom_dir(str(rom_root), console_key="ps3")
    assert str(game_dir) in roms


def test_scan_rom_dir_incomplete_pattern_falls_through(tmp_path):
    """Missing components fall through to normal recursion."""
    rom_root = tmp_path / "roms"
    rom_root.mkdir()
    game_dir = rom_root / "Incomplete Game"
    game_dir.mkdir()
    (game_dir / "PS3_GAME").mkdir()
    # No USRDIR — should recurse normally and find nothing

    roms = _scan_rom_dir(str(rom_root), console_key="ps3")
    assert str(game_dir) not in roms
    assert roms == []


def test_scan_rom_dir_non_ps3_unaffected(tmp_path):
    """Non-PS3 console_key skips dir_rom check, normal recursion."""
    rom_root = tmp_path / "roms"
    rom_root.mkdir()
    game_dir = rom_root / "Some Game"
    game_dir.mkdir()
    (game_dir / "PS3_GAME").mkdir()
    (game_dir / "PS3_GAME" / "USRDIR").mkdir()
    (game_dir / "PS3_GAME" / "USRDIR" / "data.dat").write_text("bin")

    roms = _scan_rom_dir(str(rom_root), console_key="gba")
    # Should NOT detect directory ROM; data.dat is not a recognized extension
    assert str(game_dir) not in roms
    assert roms == []


def test_scan_rom_dir_file_and_dir_together(tmp_path):
    """.iso and PS3_GAME/ entry both found in same scan."""
    rom_root = tmp_path / "roms"
    rom_root.mkdir()
    # File-style ROM
    (rom_root / "file_game.iso").write_text("iso")
    # Directory-style ROM
    game_dir = rom_root / "dir_game"
    game_dir.mkdir()
    (game_dir / "PS3_GAME").mkdir()
    (game_dir / "PS3_GAME" / "USRDIR").mkdir()
    (game_dir / "PS3_GAME" / "USRDIR" / "EBOOT.BIN").write_text("bin")

    roms = _scan_rom_dir(str(rom_root), console_key="ps3")
    assert len(roms) == 2
    assert str(rom_root / "file_game.iso") in roms
    assert str(game_dir) in roms


def test_scan_rom_dir_depth_limit_on_dir_rom(tmp_path):
    """Depth limit still applies — dir ROM at depth 4 is not detected."""
    rom_root = tmp_path / "roms"
    rom_root.mkdir()
    # Nest 4 levels deep: roms/a/b/c/My Game/PS3_GAME/...
    deep = rom_root / "a" / "b" / "c" / "My Game"
    deep.mkdir(parents=True)
    (deep / "PS3_GAME").mkdir()
    (deep / "PS3_GAME" / "USRDIR").mkdir()
    (deep / "PS3_GAME" / "USRDIR" / "EBOOT.BIN").write_text("bin")

    roms = _scan_rom_dir(str(rom_root), console_key="ps3")
    assert str(deep) not in roms


def test_scan_rom_dir_no_console_key_unchanged(tmp_path):
    """Without console_key, scanner behaves identically to before."""
    rom_root = tmp_path / "roms"
    rom_root.mkdir()
    (rom_root / "game.iso").write_text("iso")
    game_dir = rom_root / "dir_game"
    game_dir.mkdir()
    (game_dir / "PS3_GAME").mkdir()
    (game_dir / "PS3_GAME" / "USRDIR").mkdir()
    (game_dir / "PS3_GAME" / "USRDIR" / "EBOOT.BIN").write_text("bin")

    roms = _scan_rom_dir(str(rom_root))
    assert str(rom_root / "game.iso") in roms
    # EBOOT.BIN is not a recognized extension, so not found by file scan
    assert str(game_dir) not in roms
