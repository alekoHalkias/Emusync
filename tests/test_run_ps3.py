"""PS3 / RPCS3 console def + written-save adoption (#422)."""
from __future__ import annotations

import os
import time

from cli import run_ps3
from cli.consoles_data import _IMPORT_CONSOLES, _ROM_EXTENSIONS

_PS3 = next(c for c in _IMPORT_CONSOLES if c["key"] == "ps3")


def test_ps3_def():
    assert _PS3["system_keys"] == []
    assert set(_PS3["rom_extensions"]) == {"iso", "pkg"}
    assert "pkg" in _ROM_EXTENSIONS
    assert not _PS3.get("shared_memcard") and not _PS3.get("shared_state")
    assert _PS3["standalones"][0]["flatpak_id"] == "net.rpcs3.RPCS3"


def _root(tmp_path, monkeypatch):
    root = tmp_path / "savedata"
    root.mkdir()
    monkeypatch.setattr(run_ps3, "_PS3_SAVE_ROOTS", (root, tmp_path / "missing"))
    return root


def _write(folder, age=0):
    folder.mkdir()
    f = folder / "PARAM.SFO"
    f.write_text("x")
    t = time.time() - age
    os.utime(f, (t, t))


def test_resolve_single_written_folder(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    _write(root / "BLUS30001", age=1000)
    _write(root / "BLUS30002")
    assert run_ps3._resolve_written_ps3_save(time.time() - 60) == str(root / "BLUS30002")


def test_resolve_none_and_ambiguous(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    _write(root / "BLUS30001", age=1000)
    assert run_ps3._resolve_written_ps3_save(time.time() - 60) is None
    _write(root / "BLUS30002")
    _write(root / "BLUS30003")
    assert run_ps3._resolve_written_ps3_save(time.time() - 60) is None
