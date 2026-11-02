"""Detached post-game push (#725): real fork in a subprocess, no mocks."""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(not hasattr(os, "fork"), reason="POSIX only; Windows pushes inline")
def test_parent_exits_at_once_and_child_finishes_in_background(tmp_path):
    marker = tmp_path / "pushed"
    log = tmp_path / "launch.log"
    script = textwrap.dedent(f"""
        import sys, time
        sys.path.insert(0, {str(SRC)!r})
        from pathlib import Path
        from cli.run_offline import _detach_after_game
        _detach_after_game(3, Path({str(log)!r}))
        time.sleep(1.0)
        print("child done")
        Path({str(marker)!r}).write_text("ok")
    """)
    start = time.monotonic()
    proc = subprocess.run([sys.executable, "-c", script], capture_output=True, timeout=10)
    assert proc.returncode == 3
    assert time.monotonic() - start < 1.0  # parent did not wait for the push
    assert not marker.exists()
    for _ in range(50):
        if marker.exists():
            break
        time.sleep(0.1)
    assert marker.read_text() == "ok"
    assert "child done" in log.read_text()
    assert proc.stdout == b""  # child output went to the log, not the launcher's pipe
