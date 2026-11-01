"""Launch-command parsing: spaced/Windows emulator paths and spaced ROM paths (#702)."""
import os
import tempfile
from types import SimpleNamespace

from cli.common import split_launch_command
from cli.run import _resolve_launch_command


def _exe(d, name="My Emu/emu"):
    p = os.path.join(d, name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").close()
    return p


def test_quoted_spaced_exec_is_one_arg():
    with tempfile.TemporaryDirectory() as d:
        exe = _exe(d)
        assert split_launch_command(f'"{exe}" "/roms/a b.gba"') == [exe, "/roms/a b.gba"]


def test_legacy_unquoted_spaced_exec_is_rejoined():
    with tempfile.TemporaryDirectory() as d:
        exe = _exe(d)
        assert split_launch_command(f'{exe} -L "/c/core.so" "/roms/a.gba"') == [exe, "-L", "/c/core.so", "/roms/a.gba"]


def test_windows_keeps_backslashes_and_strips_quotes():
    cmd = r'"C:\Program Files\Emu\emu.exe" "D:\roms\a b.iso"'
    assert split_launch_command(cmd, windows=True) == [r"C:\Program Files\Emu\emu.exe", r"D:\roms\a b.iso"]


def test_plain_and_unknown_commands_unchanged():
    assert split_launch_command("true --flag") == ["true", "--flag"]
    assert split_launch_command("no-such-emu-xyz a b") == ["no-such-emu-xyz", "a", "b"]


def test_bare_and_single_quoted_rom_token_with_spaces_is_one_arg():
    for tok in ("%ROM%", "'%ROM%'", '"%ROM%"'):
        gd = SimpleNamespace(launch_command=f"emu {tok}", rom_source="local",
                             rom_path="/roms/my game.gba", local_rom_path="")
        assert split_launch_command(_resolve_launch_command(gd)) == ["emu", "/roms/my game.gba"]
