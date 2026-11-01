"""#699: signal handlers, hardened tar extraction, transfer timeouts."""
import io
import signal
import tarfile
from pathlib import Path

import pytest

import cli.run as run_mod
from server import sync_client
from server.sync_client import _safe_extract_tar


def _tar_with(tmp_path, build):
    p = tmp_path / "a.tar"
    with tarfile.open(p, "w") as tf:
        build(tf)
    return tarfile.open(p)


def test_setuid_bit_stripped(tmp_path):
    def build(tf):
        info = tarfile.TarInfo("f.bin")
        info.size = 3
        info.mode = 0o4755
        tf.addfile(info, io.BytesIO(b"abc"))
    dest = tmp_path / "out"
    dest.mkdir()
    with _tar_with(tmp_path, build) as tf:
        _safe_extract_tar(tf, dest)
    assert (dest / "f.bin").stat().st_mode & 0o7000 == 0


def test_fifo_member_rejected(tmp_path):
    def build(tf):
        info = tarfile.TarInfo("pipe")
        info.type = tarfile.FIFOTYPE
        tf.addfile(info)
    dest = tmp_path / "out"
    dest.mkdir()
    with _tar_with(tmp_path, build) as tf, pytest.raises(Exception):
        _safe_extract_tar(tf, dest)
    assert not (dest / "pipe").exists()


def test_interrupt_signals_registered():
    assert signal.getsignal(signal.SIGINT) is run_mod._interrupt_handler
    if hasattr(signal, "SIGHUP"):
        assert signal.getsignal(signal.SIGHUP) is run_mod._interrupt_handler


def test_interrupt_without_child_raises(monkeypatch):
    monkeypatch.setattr(run_mod._run_offline_mod, "_child_proc", None)
    with pytest.raises(KeyboardInterrupt):
        run_mod._interrupt_handler(signal.SIGINT, None)


def test_transfer_timeout_generous_lock_short():
    assert sync_client._TRANSFER_TIMEOUT.read >= 300
    src = Path(sync_client.__file__).read_text()
    assert 'f"/games/{slug}/lock"), timeout=10' in src
