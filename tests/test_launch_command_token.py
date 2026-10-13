"""`%ROM%` in a launch command follows the ROM actually in use (#518)."""
import os
import tempfile
from types import SimpleNamespace

from cli.run import _resolve_launch_command


def _gd(**kw):
    base = dict(launch_command="", rom_source="local", rom_path="", local_rom_path="")
    base.update(kw)
    return SimpleNamespace(**base)


def test_token_resolves_to_local_rom_path():
    gd = _gd(launch_command='emu "%ROM%"', rom_path="/roms/a.gba")
    assert _resolve_launch_command(gd) == 'emu "/roms/a.gba"'


def test_token_falls_back_to_offline_copy_when_share_down():
    with tempfile.TemporaryDirectory() as d:
        local = os.path.join(d, "a.gba")
        open(local, "w").close()
        gd = _gd(launch_command='emu "%ROM%"', rom_source="network",
                 rom_path="/nonexistent-share/a.gba", local_rom_path=local)
        assert _resolve_launch_command(gd) == f'emu "{local}"'


def test_token_network_unavailable_returns_none():
    gd = _gd(launch_command='emu "%ROM%"', rom_source="network", rom_path="/nonexistent-share/a.gba")
    assert _resolve_launch_command(gd) is None


def test_legacy_literal_path_still_rewritten():
    with tempfile.TemporaryDirectory() as d:
        local = os.path.join(d, "a.gba")
        open(local, "w").close()
        gd = _gd(launch_command='emu "/nonexistent-share/a.gba"', rom_source="network",
                 rom_path="/nonexistent-share/a.gba", local_rom_path=local)
        assert _resolve_launch_command(gd) == f'emu "{local}"'
