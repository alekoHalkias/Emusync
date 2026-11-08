"""emusync run never re-sends SIGTERM to the emulator; SIGKILL only after a grace (#742). Real processes."""
from __future__ import annotations

import os
import signal
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


def test_handler_never_sigterms_the_emulator_and_kills_after_grace(tmp_path, monkeypatch):
    monkeypatch.setattr(run_mod, "_STOP_GRACE_SECONDS", 0.5)
    marker = tmp_path / "sigterm"
    proc = _spawn(f"""
        import signal, time
        from pathlib import Path
        signal.signal(signal.SIGTERM, lambda *_: Path({str(marker)!r}).write_text("got"))
        print("ready", flush=True)
        time.sleep(30)
    """)
    run_offline._child_proc = proc
    start = time.monotonic()
    run_mod._sigterm_handler()
    assert proc.wait(timeout=5) == -9
    assert time.monotonic() - start >= 0.4
    assert not marker.exists()


def test_already_signaled_emulator_gets_no_second_sigterm(tmp_path):
    """Steam SIGTERMs the whole tree; RetroArch _exit()s unsaved on a second one."""
    marker = tmp_path / "exit"
    proc = _spawn(f"""
        import os, signal, time
        from pathlib import Path
        hits = []
        def on_term(*_):
            hits.append(1)
            if len(hits) > 1:
                Path({str(marker)!r}).write_text("unsaved")
                os._exit(1)
        signal.signal(signal.SIGTERM, on_term)
        print("ready", flush=True)
        while not hits:
            time.sleep(0.01)
        time.sleep(0.3)  # slow, clean shutdown
        Path({str(marker)!r}).write_text("saved")
    """)
    run_offline._child_proc = proc
    os.kill(proc.pid, signal.SIGTERM)  # Steam's signal to the emulator
    run_mod._sigterm_handler()          # Steam's signal to emusync run
    run_mod._sigterm_handler()          # repeats must not signal either
    assert proc.wait(timeout=5) == 0
    assert marker.read_text() == "saved"
