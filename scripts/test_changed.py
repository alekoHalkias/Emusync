#!/usr/bin/env python3
"""Run only the tests relevant to files changed vs. main.

Maps each changed source file to test files that mention its module name
(grep-based, not a real dependency graph — good enough for "did I touch this
area", not a substitute for the full suite CI runs on every push/PR).
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = ROOT / "tests"


def changed_files() -> list[str]:
    diffs = []
    for args in (
        ["git", "diff", "--name-only", "main...HEAD"],
        ["git", "diff", "--name-only"],
        ["git", "diff", "--name-only", "--cached"],
    ):
        out = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=False)
        diffs += out.stdout.splitlines()
    return sorted(set(f for f in diffs if f))


def main() -> int:
    changed = changed_files()
    if not changed:
        print("No changes detected vs. main — running full suite.")
        return subprocess.run([".venv/bin/python", "-m", "pytest", "tests/", "-v"], cwd=ROOT).returncode

    test_files = sorted(p.name for p in TESTS_DIR.glob("test_*.py"))
    selected: set[str] = set()

    for f in changed:
        path = Path(f)
        if path.parts[:1] == ("tests",) and path.name in test_files:
            selected.add(path.name)
            continue
        stem = path.stem  # e.g. "games", "run_switch", "save"
        for t in test_files:
            if stem and stem in t:
                selected.add(t)

    if not selected:
        print(f"Changed files: {changed}")
        print("No matching test file found by name — running full suite as a safety net.")
        return subprocess.run([".venv/bin/python", "-m", "pytest", "tests/", "-v"], cwd=ROOT).returncode

    print(f"Running {len(selected)} test file(s) matched to changed files:")
    for t in sorted(selected):
        print(f"  - {t}")
    args = [".venv/bin/python", "-m", "pytest", *(f"tests/{t}" for t in sorted(selected)), "-v"]
    return subprocess.run(args, cwd=ROOT).returncode


if __name__ == "__main__":
    sys.exit(main())
