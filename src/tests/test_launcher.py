"""The src/emusync bash launcher (#741): a venv that can't import its deps (system
Python upgraded under it) is rebuilt, and a failed rebuild errors out instead of
silently running a venv-less python3. Interpreters are sh stubs on PATH."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32" or not shutil.which("bash"), reason="bash launcher")

LAUNCHER = Path(__file__).resolve().parent.parent / "emusync"
PY = sys.executable
HEALTHY = f'#!/bin/sh\n[ "$1" = "-m" ] && [ "$2" = "pip" ] && exit 0\nexec "{PY}" "$@"\n'
BROKEN = f'#!/bin/sh\n[ "$1" = "-c" ] && {{ echo "ModuleNotFoundError: click" >&2; exit 1; }}\nexec "{PY}" "$@"\n'


def _stub(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    path.chmod(0o755)


def _layout(tmp_path: Path, venv: str | None, sys_python: str) -> tuple[Path, dict]:
    src = tmp_path / "src"
    src.mkdir()
    shutil.copy(LAUNCHER, src / "emusync")
    (src / "emusync.py").write_text("import sys\nprint('RAN', sys.argv[1:])\n")
    (src / "requirements.txt").write_text("")
    if venv is not None:
        _stub(tmp_path / ".cache/.venv/bin/python", venv)
    _stub(tmp_path / "bin/python3", sys_python)
    return src / "emusync", {**os.environ, "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}"}


def _run(launcher: Path, env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(launcher), *args], env=env, capture_output=True, text=True, timeout=60)


def test_healthy_venv_runs_through_venv_and_keeps_args(tmp_path):
    sentinel = tmp_path / "sys-python-called"
    launcher, env = _layout(tmp_path, HEALTHY, f"#!/bin/sh\ntouch {sentinel}\nexit 1\n")
    r = _run(launcher, env, "run", "Pokemon Amethyst")
    assert r.returncode == 0, r.stderr
    assert "RAN ['run', 'Pokemon Amethyst']" in r.stdout
    assert not sentinel.exists()


def test_stale_venv_is_rebuilt(tmp_path):
    venv_py = tmp_path / ".cache/.venv/bin/python"
    # `python3 -m venv --clear <dir>` recreates bin/python as a healthy interpreter.
    rebuild = f'#!/bin/sh\n[ "$1 $2 $3" = "-m venv --clear" ] || exit 1\ncat > "$4/bin/python" <<\'EOF\'\n{HEALTHY}EOF\nexit 0\n'
    launcher, env = _layout(tmp_path, BROKEN, rebuild)
    r = _run(launcher, env, "--help")
    assert r.returncode == 0, r.stderr
    assert "RAN ['--help']" in r.stdout
    assert "rebuilding" in r.stderr
    assert "ModuleNotFoundError" not in r.stderr
    assert venv_py.read_text() == HEALTHY


def test_failed_rebuild_errors_instead_of_bare_python3(tmp_path):
    launcher, env = _layout(tmp_path, BROKEN, '#!/bin/sh\n[ "$1" = "--version" ] && echo "Python 3.99.0"\nexit 1\n')
    r = _run(launcher, env, "--help")
    assert r.returncode == 1
    assert "RAN" not in r.stdout
    assert ".venv" in r.stderr and "could not rebuild" in r.stderr and "3.99.0" in r.stderr


def test_no_venv_falls_back_to_system_python(tmp_path):
    launcher, env = _layout(tmp_path, None, f'#!/bin/sh\nexec "{PY}" "$@"\n')
    r = _run(launcher, env, "--help")
    assert r.returncode == 0, r.stderr
    assert "RAN ['--help']" in r.stdout
