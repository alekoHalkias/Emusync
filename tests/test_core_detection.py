"""Regression tests for RetroArch core recognition (issue #400).

Two bugs: detection returned only the FIRST installed core per system (so a
second installed SNES core never appeared in the wizard), and any core absent
from the hardcoded seed lists was invisible entirely. Detection now returns
every installed core from the seed lists AND discovers unlisted cores from
RetroArch's own `.info` metadata, matched to a console via its libretro
`database` names.
"""
from __future__ import annotations

from cli.consoles_data import _IMPORT_CONSOLES, _IMPORT_SYSTEMS
from cli.detect import (
    _detect_emulators_for_console,
    _discover_cores_by_info,
    _find_installed_cores,
)

_SNES_DEF = next(c for c in _IMPORT_CONSOLES if c["key"] == "snes")
_PSX_DEF = next(c for c in _IMPORT_CONSOLES if c["key"] == "psx")
_GENESIS_DEF = next(c for c in _IMPORT_CONSOLES if c["key"] == "genesis")
_SMS_DEF = next(c for c in _IMPORT_CONSOLES if c["key"] == "sms")


def _install_core(cores_dir, lib: str) -> None:
    cores_dir.mkdir(parents=True, exist_ok=True)
    (cores_dir / f"{lib}.so").write_text("")


def _write_info(info_dir, lib: str, corename: str, database: str) -> None:
    info_dir.mkdir(parents=True, exist_ok=True)
    (info_dir / f"{lib}.info").write_text(
        f'display_name = "System ({corename})"\n'
        f'corename = "{corename}"\n'
        f'database = "{database}"\n'
    )


def test_find_installed_cores_returns_all_matches(tmp_path):
    """The old _find_installed_core stopped at the first hit — with both
    Snes9x and bsnes installed, only Snes9x ever appeared."""
    _install_core(tmp_path, "snes9x_libretro")
    _install_core(tmp_path, "bsnes_libretro")
    found = _find_installed_cores(str(tmp_path), _IMPORT_SYSTEMS["sfc"])
    assert [c["folder"] for c in found] == ["Snes9x", "bsnes"]


def test_snes9x2005_plus_is_in_seed_list(tmp_path):
    """The core that triggered #400: a user whose only SNES core was
    snes9x2005_plus saw no RetroArch option at all."""
    _install_core(tmp_path, "snes9x2005_plus_libretro")
    found = _find_installed_cores(str(tmp_path), _IMPORT_SYSTEMS["sfc"])
    assert [c["folder"] for c in found] == ["Snes9x 2005 Plus"]


def test_discover_cores_by_info_matches_console_databases(tmp_path):
    """An unlisted core with a .info naming the console's database is
    recognized, with the save folder taken from `corename`."""
    cores = tmp_path / "cores"
    _install_core(cores, "somenewcore_libretro")
    _write_info(cores, "somenewcore_libretro", "SomeNewCore",
                "Nintendo - Super Nintendo Entertainment System")
    found = _discover_cores_by_info(str(cores), [str(cores)], _SNES_DEF["databases"])
    assert len(found) == 1
    assert found[0]["folder"] == "SomeNewCore"
    assert found[0]["lib"].endswith("somenewcore_libretro.so")


def test_discover_cores_by_info_rejects_wrong_console(tmp_path):
    """Flycast is a Dreamcast core — its .info databases must not match the
    PSX console (the old hardcoded list wrongly offered it for PS1)."""
    cores = tmp_path / "cores"
    _install_core(cores, "flycast_libretro")
    _write_info(cores, "flycast_libretro", "Flycast",
                "Sega - Dreamcast|Sega - NAOMI|Sega - Atomiswave")
    assert _discover_cores_by_info(str(cores), [str(cores)], _PSX_DEF["databases"]) == []


def test_discover_cores_by_info_multi_database_core_matches_both_consoles(tmp_path):
    """A multi-system core (Genesis Plus GX) matches every console whose
    databases intersect its .info database list."""
    cores = tmp_path / "cores"
    _install_core(cores, "genesis_plus_gx_libretro")
    _write_info(cores, "genesis_plus_gx_libretro", "Genesis Plus GX",
                "Sega - Mega Drive - Genesis|Sega - Master System - Mark III|Sega - Game Gear")
    for console_def in (_GENESIS_DEF, _SMS_DEF):
        found = _discover_cores_by_info(str(cores), [str(cores)], console_def["databases"])
        assert [c["folder"] for c in found] == ["Genesis Plus GX"]


def test_discover_cores_by_info_skips_core_without_info(tmp_path):
    cores = tmp_path / "cores"
    _install_core(cores, "mysterycore_libretro")
    assert _discover_cores_by_info(str(cores), [str(cores)], _SNES_DEF["databases"]) == []


def test_discover_cores_by_info_searches_info_dirs_in_order(tmp_path):
    """Info files often live in a separate dir (`libretro_info_path`,
    /usr/share/libretro/info) rather than next to the .so files."""
    cores = tmp_path / "cores"
    info = tmp_path / "info"
    _install_core(cores, "somenewcore_libretro")
    _write_info(info, "somenewcore_libretro", "SomeNewCore",
                "Nintendo - Super Nintendo Entertainment System")
    found = _discover_cores_by_info(str(cores), [str(info)], _SNES_DEF["databases"])
    assert [c["folder"] for c in found] == ["SomeNewCore"]


def test_detect_emulators_lists_every_installed_core(tmp_path, monkeypatch):
    """End-to-end through _detect_emulators_for_console: seeded cores appear
    first (all of them), then info-discovered unlisted cores — each with its
    own per-core save/state subfolder."""
    cores = tmp_path / "cores"
    _install_core(cores, "snes9x_libretro")
    _install_core(cores, "bsnes_libretro")
    _install_core(cores, "brandnew_libretro")  # not in any seed list
    _write_info(cores, "brandnew_libretro", "BrandNew",
                "Nintendo - Super Nintendo Entertainment System")
    monkeypatch.setattr("cli.detect._detect_retroarch", lambda: [{
        "type": "native", "label": "RetroArch", "exec_path": "/usr/bin/retroarch",
        "save_dir": str(tmp_path / "saves"), "states_dir": str(tmp_path / "states"),
        "cores_dir": str(cores), "info_dirs": [str(cores)], "rom_dirs": [],
    }])

    options = _detect_emulators_for_console(_SNES_DEF)

    folders = [o["core_folder"] for o in options]
    assert folders == ["Snes9x", "bsnes", "BrandNew"]
    for o in options:
        assert o["save_dir"] == str(tmp_path / "saves" / o["core_folder"])
        assert o["state_dir"] == str(tmp_path / "states" / o["core_folder"])


def test_flycast_removed_from_psx_seed_lists():
    """Regression: flycast (Dreamcast) sat in the iso/chd disc systems, so a
    PS1 import could be offered a Dreamcast core."""
    for sys_key in _PSX_DEF["system_keys"]:
        libs = {c["lib"] for c in _IMPORT_SYSTEMS[sys_key]["cores"]}
        assert "flycast_libretro" not in libs


def test_every_console_def_declares_databases():
    """Info-file matching only works for a console that names its libretro
    databases — every seeded console must declare at least one."""
    for console_def in _IMPORT_CONSOLES:
        assert console_def.get("databases"), f"{console_def['key']} has no databases"
