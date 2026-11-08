"""SIGTERM stops the emulator gracefully, SIGKILL only after a grace (#742). Real processes."""
from __future__ import annotations

import subprocess
import sys
import textwrap
import time

import pytest

from cli import run as run_mod
from cli import run_offline


def _spawn(body: str) -> subprocess.Popen:
    code = textwrap.dedent(body)
    proc = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE)
    assert proc.stdout.readline().strip() == b"ready"  # handlers installed
    return proc


@pytest.fixture(autouse=True)
def _clear_child():
    yield
    run_offline._child_proc = None


def test_sigterm_lets_the_emulator_save_before_exiting(tmp_path):
    marker = tmp_path / "saved"
    proc = _spawn(f"""
        import signal, sys, time
        from pathlib import Path
        def bye(*_):
            Path({str(marker)!r}).write_text("sram")
            sys.exit(0)
        signal.signal(signal.SIGTERM, bye)
        print("ready", flush=True)
        time.sleep(30)
    """)
    run_offline._child_proc = proc
    run_mod._sigterm_handler()
    assert proc.wait(timeout=5) == 0
    assert marker.read_text() == "sram"


def test_emulator_ignoring_sigterm_is_killed_after_the_grace(tmp_path, monkeypatch):
    monkeypatch.setattr(run_mod, "_STOP_GRACE_SECONDS", 0.5)
    proc = _spawn("""
        import signal, time
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        print("ready", flush=True)
        time.sleep(30)
    """)
    run_offline._child_proc = proc
    start = time.monotonic()
    run_mod._sigterm_handler()
    assert proc.wait(timeout=5) == -9
    assert time.monotonic() - start >= 0.4
