"""Dreamcast / GameCube-Wii / PSP console support (issue #402).

Three new shared-save consoles riding the PS2 console-card pipeline
(#291–#295): each console's def matches its core via .info databases (#400),
its shared card resolves to a per-console path (VMU file / Dolphin GC folder /
PPSSPP SAVEDATA folder), and — unlike PS2 — save STATES stay per-game.
"""
from __future__ import annotations

import io
import tarfile

from cli.consoles_data import _IMPORT_CONSOLES, _ROM_EXTENSIONS
from cli.detect import _discover_cores_by_info, _resolve_shared_memcard_save_state
from cli.run import _SHARED_MEMCARD_CONSOLES, _SHARED_STATE_CONSOLES
from server.sync_client import _write_memcard, memcard_bytes

_BY_KEY = {c["key"]: c for c in _IMPORT_CONSOLES}


def _install_core(cores_dir, lib: str) -> None:
    cores_dir.mkdir(parents=True, exist_ok=True)
    (cores_dir / f"{lib}.so").write_text("")


def _write_info(info_dir, lib: str, corename: str, database: str) -> None:
    info_dir.mkdir(parents=True, exist_ok=True)
    (info_dir / f"{lib}.info").write_text(
        f'corename = "{corename}"\ndatabase = "{database}"\n'
    )


# ── console defs ───────────────────────────────────────────────────────────────

def test_new_console_defs_follow_ps2_pattern():
    """No system_keys (so PSX disc cores never surface for shared .iso/.chd),
    explicit rom_extensions, databases for .info matching."""
    expectations = {
        "dc": ({"gdi", "cdi", "chd", "cue"}, ["Sega - Dreamcast"]),
        "gamecube": ({"iso", "gcm", "rvz", "wbfs"},
                     ["Nintendo - GameCube", "Nintendo - Wii"]),
        "psp": ({"iso", "cso", "pbp"}, ["Sony - PlayStation Portable"]),
    }
    for key, (exts, databases) in expectations.items():
        cdef = _BY_KEY[key]
        assert cdef["system_keys"] == []
        assert set(cdef["rom_extensions"]) == exts
        assert cdef["databases"] == databases
        for ext in exts:
            assert ext in _ROM_EXTENSIONS


def test_shared_membership_matches_console_abbrs():
    """run.py keys the shared sets by the game's stored console abbr — a
    mismatch with the def's abbr silently disables card sync."""
    shared_abbrs = {_BY_KEY[k]["abbr"] for k in ("ps2", "dc", "gamecube", "psp")}
    assert shared_abbrs == _SHARED_MEMCARD_CONSOLES
    # Only PS2 shares its states; dc/gamecube/psp states are per-game.
    assert _SHARED_STATE_CONSOLES == {"PS2"}


# ── core ↔ console matching via .info databases (#400) ────────────────────────

def test_new_cores_match_their_console_and_not_psx(tmp_path):
    cores = tmp_path / "cores"
    _install_core(cores, "flycast_libretro")
    _write_info(cores, "flycast_libretro", "Flycast",
                "Sega - Dreamcast|Sega - NAOMI|Sega - Atomiswave")
    _install_core(cores, "dolphin_libretro")
    _write_info(cores, "dolphin_libretro", "dolphin-emu",
                "Nintendo - GameCube|Nintendo - Wii")
    _install_core(cores, "ppsspp_libretro")
    _write_info(cores, "ppsspp_libretro", "PPSSPP", "Sony - PlayStation Portable")

    def folders_for(console_key: str) -> set[str]:
        found = _discover_cores_by_info(
            str(cores), [str(cores)], _BY_KEY[console_key]["databases"])
        return {c["folder"] for c in found}

    assert folders_for("dc") == {"Flycast"}
    assert folders_for("gamecube") == {"dolphin-emu"}  # both GC and Wii databases hit
    assert folders_for("psp") == {"PPSSPP"}
    assert folders_for("psx") == set()  # none of them are PS1 cores


# ── shared-card path resolution ────────────────────────────────────────────────

def test_dc_card_resolves_to_vmu_a1(tmp_path):
    save_root = tmp_path / "saves"
    (save_root).mkdir()
    (save_root / "vmu_save_A1.bin").write_bytes(b"vmu")
    emu = {"save_dir": str(save_root / "Flycast"), "core_folder": "Flycast",
           "state_dir": None}
    save_match, _ = _resolve_shared_memcard_save_state(emu, "DC")
    assert save_match == {"path": str(save_root / "vmu_save_A1.bin"), "exists": True}


def test_dc_card_defaults_to_saves_root_when_missing(tmp_path):
    emu = {"save_dir": str(tmp_path / "saves" / "Flycast"), "core_folder": "Flycast",
           "state_dir": None}
    save_match, _ = _resolve_shared_memcard_save_state(emu, "DC")
    assert save_match["path"] == str(tmp_path / "saves" / "vmu_save_A1.bin")
    assert save_match["exists"] is False


def test_gamecube_card_prefers_existing_candidate(tmp_path):
    """Dolphin's cards may live under the RetroArch system dir — the resolver
    probes candidates and picks the one that exists."""
    system_dir = tmp_path / "system"
    gc_dir = system_dir / "dolphin-emu" / "Userdata" / "GC"
    gc_dir.mkdir(parents=True)
    (gc_dir / "MemoryCardA.USA.raw").write_bytes(b"card")
    emu = {"save_dir": str(tmp_path / "saves" / "dolphin-emu"),
           "core_folder": "dolphin-emu", "state_dir": None,
           "system_dir": str(system_dir)}
    save_match, _ = _resolve_shared_memcard_save_state(emu, "GC")
    assert save_match == {"path": str(gc_dir), "exists": True}


def test_gamecube_standalone_dolphin_def_follows_pcsx2_pattern():
    """Standalone Dolphin (#415) mirrors _PCSX2's shape: native_bins/flatpak
    fields present, registered as the gamecube console's standalone."""
    from cli.consoles_data import _DOLPHIN
    assert _DOLPHIN["native_bins"]
    assert _DOLPHIN["flatpak_id"] == "org.DolphinEmu.dolphin-emu"
    assert _DOLPHIN["dirs"]["native"]["save"] == "~/.local/share/dolphin-emu/GC"
    assert _BY_KEY["gamecube"]["standalones"] == [_DOLPHIN]


def test_gamecube_standalone_dolphin_detected_via_flatpak_when_no_native_bin(monkeypatch, tmp_path):
    """No native dolphin-emu binary installed, but the flatpak is — detection
    surfaces the flatpak entry with its own save/state dirs (#415)."""
    from cli.consoles_data import _DOLPHIN
    from cli.detect import _detect_emulators_for_console

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr("cli.detect.Path.home", staticmethod(lambda: home))
    # Force every native_bins candidate to appear absent, regardless of what's
    # actually installed on the machine running this test.
    monkeypatch.setattr("cli.detect.os.path.exists", lambda p: False)

    class _FakeResult:
        stdout = "org.DolphinEmu.dolphin-emu\n"

    monkeypatch.setattr("cli.detect.subprocess.run", lambda *a, **k: _FakeResult())

    console_def = {"standalones": [_DOLPHIN], "system_keys": []}
    options = _detect_emulators_for_console(console_def)

    assert len(options) == 1
    opt = options[0]
    assert opt["id"] == "dolphin-flatpak"
    assert opt["exec_path"] == "flatpak run org.DolphinEmu.dolphin-emu"
    assert opt["save_dir"] == str(home / ".var" / "app" / "org.DolphinEmu.dolphin-emu" / "data" / "dolphin-emu" / "GC")
    assert opt["state_dir"] == str(home / ".var" / "app" / "org.DolphinEmu.dolphin-emu" / "data" / "dolphin-emu" / "StateSaves")


def test_gamecube_standalone_dolphin_lists_native_and_flatpak_together(monkeypatch, tmp_path):
    """Both a native binary and the flatpak are installed — detection must
    list both as separate options, matching RetroArch's own native+flatpak
    detection, instead of the native entry silently hiding the flatpak one
    (regression: the standalone loop used to gate the flatpak check behind
    `not found`, unlike every other detection path in this file) (#415)."""
    from cli.consoles_data import _DOLPHIN
    from cli.detect import _detect_emulators_for_console

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr("cli.detect.Path.home", staticmethod(lambda: home))
    native_bin = _DOLPHIN["native_bins"][0]
    monkeypatch.setattr("cli.detect.os.path.exists", lambda p: p == native_bin)

    class _FakeResult:
        stdout = "org.DolphinEmu.dolphin-emu\n"

    monkeypatch.setattr("cli.detect.subprocess.run", lambda *a, **k: _FakeResult())

    console_def = {"standalones": [_DOLPHIN], "system_keys": []}
    options = _detect_emulators_for_console(console_def)

    ids = {opt["id"] for opt in options}
    assert ids == {"dolphin-native", "dolphin-flatpak"}


def test_gamecube_standalone_card_resolves_to_save_dir_directly(tmp_path):
    """Standalone Dolphin's save_dir IS the GC card folder already — no
    core_folder means no 'User/GC' subpath should be appended (#415)."""
    gc_dir = tmp_path / "dolphin-emu" / "GC"
    gc_dir.mkdir(parents=True)
    (gc_dir / "MemoryCardA.USA.raw").write_bytes(b"card")
    emu = {"save_dir": str(gc_dir), "state_dir": None}
    save_match, _ = _resolve_shared_memcard_save_state(emu, "GC")
    assert save_match == {"path": str(gc_dir), "exists": True}


def test_gamecube_standalone_card_defaults_to_save_dir_when_missing(tmp_path):
    gc_dir = tmp_path / "dolphin-emu" / "GC"
    emu = {"save_dir": str(gc_dir), "state_dir": None}
    save_match, _ = _resolve_shared_memcard_save_state(emu, "GC")
    assert save_match == {"path": str(gc_dir), "exists": False}


def test_psp_card_resolves_to_savedata_folder(tmp_path):
    save_root = tmp_path / "saves"
    savedata = save_root / "PPSSPP" / "PSP" / "SAVEDATA"
    savedata.mkdir(parents=True)
    emu = {"save_dir": str(save_root / "PPSSPP"), "core_folder": "PPSSPP",
           "state_dir": None}
    save_match, _ = _resolve_shared_memcard_save_state(emu, "PSP")
    assert save_match == {"path": str(savedata), "exists": True}


def test_ps2_card_resolution_unchanged(tmp_path):
    """Regression: the per-console resolver must not disturb the PS2 path."""
    memcards = tmp_path / "memcards"
    memcards.mkdir()
    (memcards / "Mcd001.ps2").write_bytes(b"ps2card")
    emu = {"save_dir": str(memcards), "state_dir": None}
    save_match, _ = _resolve_shared_memcard_save_state(emu, "PS2")
    assert save_match == {"path": str(memcards / "Mcd001.ps2"), "exists": True}


# ── folder cards round-trip through the existing memcard machinery ────────────

def test_psp_savedata_folder_card_round_trips(tmp_path):
    """A PPSSPP SAVEDATA tree (nested per-game folders) packs and restores
    losslessly via the same tar path PCSX2 folder cards use (#320)."""
    src = tmp_path / "SAVEDATA"
    (src / "ULUS10041DATA00").mkdir(parents=True)
    (src / "ULUS10041DATA00" / "DATA.BIN").write_bytes(b"save-bytes")
    (src / "ULUS10041DATA00" / "PARAM.SFO").write_bytes(b"sfo")
    (src / "UCUS98687DATA01").mkdir()
    (src / "UCUS98687DATA01" / "DATA.BIN").write_bytes(b"other-save")

    data = memcard_bytes(src)
    names = {m.name for m in tarfile.open(fileobj=io.BytesIO(data)).getmembers()}
    assert names == {"ULUS10041DATA00/DATA.BIN", "ULUS10041DATA00/PARAM.SFO",
                     "UCUS98687DATA01/DATA.BIN"}

    dest = tmp_path / "restored" / "SAVEDATA"
    dest.mkdir(parents=True)
    _write_memcard(dest, data)
    assert (dest / "ULUS10041DATA00" / "DATA.BIN").read_bytes() == b"save-bytes"
    assert (dest / "UCUS98687DATA01" / "DATA.BIN").read_bytes() == b"other-save"
