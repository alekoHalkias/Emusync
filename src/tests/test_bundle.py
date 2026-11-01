"""Guards the AppImage's bundled CLI (#677): the extraResources list must not drift
from src/, and the runtime requirements must not carry test packages."""
import json
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent
NOT_BUNDLED = {"gui", "tests", "scripts", "docs", "__pycache__"}


def _filter() -> list[str]:
    pkg = json.loads((SRC / "gui" / "package.json").read_text(encoding="utf-8"))
    (res,) = pkg["build"]["extraResources"]
    assert res["from"] == ".." and res["to"] == "src"
    return res["filter"]


def test_bundle_covers_every_python_package():
    patterns = _filter()
    for d in sorted(p for p in SRC.iterdir() if p.is_dir() and p.name not in NOT_BUNDLED):
        if any(d.rglob("*.py")) or any(d.rglob("*.json")):
            assert f"{d.name}/**/*" in patterns, f"src/{d.name}/ is not in build.extraResources"


def test_bundle_includes_entrypoints():
    patterns = _filter()
    for name in ("emusync.py", "emusync", "requirements.txt"):
        assert name in patterns and (SRC / name).exists()


def test_runtime_requirements_have_no_test_packages():
    runtime = (SRC / "requirements.txt").read_text()
    assert "pytest" not in runtime
    dev = (SRC / "requirements-dev.txt").read_text()
    assert "-r requirements.txt" in dev and "pytest" in dev
