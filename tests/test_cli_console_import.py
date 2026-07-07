"""Unit tests for the CLI console-import wizard's PS2/shared-memcard handling
(issue #361): ROM extension matching falling back to `rom_extensions`, standalone
emulator detection reading `dirs.native`/`dirs.flatpak` instead of a nonexistent
top-level key, and shared-memcard save/state resolution.
"""
from __future__ import annotations

import os

from cli.consoles_data import _IMPORT_CONSOLES
from cli.detect import (
    _detect_emulators_for_console,
    _dir_has_any_file,
    _find_first_by_ext,
    _resolve_shared_memcard_save_state,
)

_PS2_DEF = next(c for c in _IMPORT_CONSOLES if c["key"] == "ps2")


def test_ps2_console_def_has_no_system_keys_but_has_rom_extensions():
    assert _PS2_DEF["system_keys"] == []
    assert _PS2_DEF["rom_extensions"] == ["iso", "chd", "bin"]


def test_extension_matching_falls_back_to_rom_extensions():
    rom_ext_set = set(_PS2_DEF.get("rom_extensions") or _PS2_DEF["system_keys"])
    assert rom_ext_set == {"iso", "chd", "bin"}


def test_extension_matching_uses_system_keys_when_no_rom_extensions():
    gba_def = next(c for c in _IMPORT_CONSOLES if c["key"] == "gba")
    rom_ext_set = set(gba_def.get("rom_extensions") or gba_def["system_keys"])
    assert rom_ext_set == {"gba"}


def test_detect_standalone_native_reads_dirs_template(tmp_path, monkeypatch):
    """Previously crashed with KeyError('save_dir') — the PCSX2 def only has
    `dirs.native.save`/`dirs.native.state`, not a top-level `save_dir`."""
    fake_bin = tmp_path / "pcsx2-qt"
    fake_bin.write_text("")
    save_dir = tmp_path / "memcards"
    state_dir = tmp_path / "sstates"

    console_def = {
        "standalones": [{
            "id": "pcsx2", "label": "PCSX2",
            "native_bins": [str(fake_bin)],
            "flatpak_id": "net.pcsx2.PCSX2",
            "flatpak_exec": "flatpak run net.pcsx2.PCSX2",
            "dirs": {
                "native": {"save": str(save_dir), "state": str(state_dir)},
                "flatpak": {"save": "", "state": ""},
            },
        }],
        "system_keys": [],
    }

    options = _detect_emulators_for_console(console_def)

    assert len(options) == 1
    assert options[0]["save_dir"] == str(save_dir)
    assert options[0]["state_dir"] == str(state_dir)
    assert options[0]["exec_path"] == str(fake_bin)


def test_detect_standalone_expands_tilde_native_bins(monkeypatch, tmp_path):
    home = tmp_path / "home"
    (home / ".local" / "bin").mkdir(parents=True)
    fake_bin = home / ".local" / "bin" / "pcsx2-qt"
    fake_bin.write_text("")
    monkeypatch.setattr("cli.detect.Path.home", staticmethod(lambda: home))

    console_def = {
        "standalones": [{
            "id": "pcsx2", "label": "PCSX2",
            "native_bins": ["~/.local/bin/pcsx2-qt"],
            "flatpak_id": "net.pcsx2.PCSX2",
            "flatpak_exec": "flatpak run net.pcsx2.PCSX2",
            "dirs": {"native": {"save": "~/.config/PCSX2/memcards"}, "flatpak": {}},
        }],
        "system_keys": [],
    }

    options = _detect_emulators_for_console(console_def)

    assert len(options) == 1
    assert options[0]["exec_path"] == str(fake_bin)
    assert options[0]["save_dir"] == str(home / ".config" / "PCSX2" / "memcards")


def test_find_first_by_ext_finds_existing_card(tmp_path):
    (tmp_path / "Mcd001.ps2").write_text("card")
    found = _find_first_by_ext(str(tmp_path), ".ps2")
    assert found == str(tmp_path / "Mcd001.ps2")


def test_find_first_by_ext_missing_dir_returns_none(tmp_path):
    assert _find_first_by_ext(str(tmp_path / "nope"), ".ps2") is None


def test_dir_has_any_file(tmp_path):
    assert _dir_has_any_file(str(tmp_path)) is False
    (tmp_path / "SLUS-20062 (ABCD1234).00.p2s").write_text("state")
    assert _dir_has_any_file(str(tmp_path)) is True


def test_resolve_shared_memcard_save_state_finds_existing_card(tmp_path):
    save_dir = tmp_path / "memcards"
    state_dir = tmp_path / "sstates"
    save_dir.mkdir()
    state_dir.mkdir()
    card = save_dir / "Mcd001.ps2"
    card.write_text("card")
    (state_dir / "SLUS-20062 (ABCD1234).00.p2s").write_text("state")

    emu = {"save_dir": str(save_dir), "state_dir": str(state_dir)}
    save_match, state_match = _resolve_shared_memcard_save_state(emu, "PS2")

    assert save_match == {"path": str(card), "exists": True}
    assert state_match == {"path": str(state_dir), "exists": True}


def test_resolve_shared_memcard_save_state_falls_back_when_no_card(tmp_path):
    save_dir = tmp_path / "memcards"
    save_dir.mkdir()

    emu = {"save_dir": str(save_dir), "state_dir": None}
    save_match, state_match = _resolve_shared_memcard_save_state(emu, "PS2")

    assert save_match == {"path": str(save_dir / "Mcd001.ps2"), "exists": False}
    assert state_match is None


def test_resolve_shared_memcard_save_state_ignores_non_ps2_files(tmp_path):
    save_dir = tmp_path / "memcards"
    save_dir.mkdir()
    (save_dir / "readme.txt").write_text("not a card")

    emu = {"save_dir": str(save_dir), "state_dir": None}
    save_match, _ = _resolve_shared_memcard_save_state(emu, "PS2")

    assert save_match["exists"] is False
    assert os.path.basename(save_match["path"]) == "Mcd001.ps2"
