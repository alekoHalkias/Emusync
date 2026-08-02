"""Switch per-title save sync (#419).

Covers `cli.run_switch._resolve_written_switch_save` (pure filesystem logic —
which title folder a play session actually wrote to), mirroring
tests/test_wii_save_sync.py for the analogous Wii NAND resolver.
"""
from __future__ import annotations

import time
from pathlib import Path

from cli.run_switch import (
    _resolve_written_switch_save,
    _seed_switch_save,
    _switch_title_id_from_rom,
)


def _make_title(nand_root: Path, profile_id: str, title_id: str) -> Path:
    title_dir = nand_root / profile_id / title_id
    title_dir.mkdir(parents=True)
    return title_dir


def test_resolves_the_single_title_written_this_session(monkeypatch, tmp_path):
    nand_root = tmp_path / "save"
    monkeypatch.setattr("cli.run_switch._SWITCH_NAND_ROOTS", (nand_root,))

    title_dir = _make_title(nand_root, "0000000000000000000000000000001", "01006A800016E000")
    since = time.time()
    time.sleep(0.01)
    (title_dir / "save_data.bin").write_text("save data")

    result = _resolve_written_switch_save(since)

    assert result == str(title_dir)


def test_returns_none_when_nothing_written_this_session(monkeypatch, tmp_path):
    nand_root = tmp_path / "save"
    monkeypatch.setattr("cli.run_switch._SWITCH_NAND_ROOTS", (nand_root,))
    _make_title(nand_root, "profile1", "01006A800016E000")  # exists, but untouched

    result = _resolve_written_switch_save(time.time())

    assert result is None


def test_ambiguous_multi_title_write_warns_and_skips(monkeypatch, tmp_path, capsys):
    nand_root = tmp_path / "save"
    monkeypatch.setattr("cli.run_switch._SWITCH_NAND_ROOTS", (nand_root,))

    title_a = _make_title(nand_root, "profile1", "01006A800016E000")
    title_b = _make_title(nand_root, "profile1", "0100000000010000")
    since = time.time()
    time.sleep(0.01)
    (title_a / "save_data.bin").write_text("a")
    (title_b / "save_data.bin").write_text("b")

    result = _resolve_written_switch_save(since)

    assert result is None
    assert "multiple Switch titles" in capsys.readouterr().err


def test_no_profile_folder_returns_none(tmp_path, monkeypatch):
    nand_root = tmp_path / "save"  # never created — no profile has run Eden yet
    monkeypatch.setattr("cli.run_switch._SWITCH_NAND_ROOTS", (nand_root,))

    result = _resolve_written_switch_save(time.time())

    assert result is None


# ── pre-seeding an existing server save before first launch (#443) ────────────

def test_switch_title_id_from_rom_extracts_bracketed_id():
    rom = "/roms/switch/Pokemon Legends Arceus [0100000011D90000][v0].nsp"
    assert _switch_title_id_from_rom(rom) == "0100000011D90000"


def test_switch_title_id_from_rom_none_when_untagged():
    assert _switch_title_id_from_rom("/roms/switch/some_game.nsp") is None


class _FakeSeedClient:
    def __init__(self, fail_for: set[str] = frozenset()):
        self.calls: list[tuple[str, str]] = []
        self._fail_for = fail_for

    def pull_save(self, slug, path):
        self.calls.append((slug, path))
        if path in self._fail_for:
            raise RuntimeError("boom")
        return True, "server-hash"


def test_seed_switch_save_writes_into_every_existing_profile(monkeypatch, tmp_path):
    nand_root = tmp_path / "save"
    monkeypatch.setattr("cli.run_switch._SWITCH_NAND_ROOTS", (nand_root,))
    profile_a = nand_root / "profile-a"
    profile_b = nand_root / "profile-b"
    profile_a.mkdir(parents=True)
    profile_b.mkdir(parents=True)

    rom = "/roms/switch/Pokemon Legends Arceus [0100000011D90000][v0].nsp"
    client = _FakeSeedClient()

    seeded = _seed_switch_save(client, "pokemon-legends-arceus", rom)

    assert sorted(seeded) == sorted([
        str(profile_a / "0100000011D90000"),
        str(profile_b / "0100000011D90000"),
    ])
    assert {p for _, p in client.calls} == set(seeded)


def test_seed_switch_save_returns_empty_when_title_id_unavailable(tmp_path):
    client = _FakeSeedClient()

    seeded = _seed_switch_save(client, "some-game", "/roms/switch/untagged.nsp")

    assert seeded == []
    assert client.calls == []


def test_seed_switch_save_tolerates_a_failed_profile(monkeypatch, tmp_path):
    nand_root = tmp_path / "save"
    monkeypatch.setattr("cli.run_switch._SWITCH_NAND_ROOTS", (nand_root,))
    profile_a = nand_root / "profile-a"
    profile_b = nand_root / "profile-b"
    profile_a.mkdir(parents=True)
    profile_b.mkdir(parents=True)

    rom = "/roms/switch/game [0100000011D90000].nsp"
    failing_dest = str(profile_a / "0100000011D90000")
    client = _FakeSeedClient(fail_for={failing_dest})

    seeded = _seed_switch_save(client, "some-game", rom)

    assert seeded == [str(profile_b / "0100000011D90000")]


def test_finds_title_under_emudeck_style_second_root(monkeypatch, tmp_path):
    """Regression (#441): EmuDeck-managed installs (common on Steam Deck)
    redirect Eden's whole data directory to ~/Emulation/storage/eden/ instead
    of the XDG default ~/.local/share/eden/ — confirmed from a real deck's
    `ps aux` showing Eden's load/ folder living under
    ~/Emulation/storage/eden/. Both roots must be checked, the same way
    native/flatpak both are for every other standalone emulator, or a
    session's save is silently never found on such a device."""
    xdg_root = tmp_path / "xdg" / "save"
    emudeck_root = tmp_path / "emudeck" / "save"
    monkeypatch.setattr("cli.run_switch._SWITCH_NAND_ROOTS", (xdg_root, emudeck_root))

    # xdg_root doesn't even exist — matches a real EmuDeck install where
    # nothing was ever written to the XDG-default location at all.
    title_dir = _make_title(emudeck_root, "PROFILE", "0100000011D90000")
    since = time.time()
    time.sleep(0.01)
    (title_dir / "main").write_text("save data")

    result = _resolve_written_switch_save(since)

    assert result == str(title_dir)
