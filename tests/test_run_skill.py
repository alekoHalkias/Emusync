"""Tests for scripts/run-skill.sh — subprocess-driven, stdlib only.

Each test creates a temp directory with a handoff file, puts a fake
``claude`` script on PATH, and drives ``scripts/run-skill.sh`` through
subprocess.  No product code or DB is touched.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional


def _write_handoff(d: Path, status: str, issue: str = "999") -> Path:
    """Create a minimal handoff file."""
    p = d / f"{issue}-handoff.md"
    p.write_text(
        f"# Handoff: #{issue} Test\n\n"
        "## Metadata\n"
        f"  - Issue: #{issue}\n"
        f"  - Status: {status}\n"
        "## 1. Issue\nSummary: test\n"
        "## 2. Design\nScope: test\n"
        "## 3. Frontend Plan\nn/a\n"
        "## 4. Backend Plan\nn/a\n"
        "## 5. Merged Plan\nnone\n"
        "## 6. Testing Plan\ntest\n"
        "## 7. Test Design\ntest\n"
        "## 8. Implementation Steps\nsteps\n"
        "## 9. Review\n### Findings: TBD\n"
        "## 10. Ship\nStatus: pending\n"
        "## 11. Fix Attempts\nnone\n"
        "## 12. Log\n"
    )
    return p


def _fake_clude_factory(
    transitions: dict[str, str],
    exit_status: int = 0,
) -> str:
    """Return a shell script that maps skill→next-status and records calls."""
    # Build case labels from status→next-status transitions
    branches = "\n".join(
        f'  "{k}") next="{v}" ;;' for k, v in transitions.items()
    )
    return (
        "#!/usr/bin/env bash\n"
        "# Save the real claude path before PATH is shadowed by the tmpdir.\n"
        'REAL_CLAUDE=$(command -v claude || true)\n'
        "# Record which skill is being invoked\n"
        'skill=""\n'
        'for arg in "$@"; do\n'
        '  case "$arg" in\n'
        '    */fplan*) skill="fplan" ;;\n'
        '    */bplan*) skill="bplan" ;;\n'
        '    */tplan*) skill="tplan" ;;\n'
        '    */plan*)  skill="plan"  ;;\n'
        '    */design*) skill="design" ;;\n'
        '    */implement*) skill="implement" ;;\n'
        '    */review*) skill="review" ;;\n'
        '    */ship*) skill="ship" ;;\n'
        '  esac\n'
        '  if [ -n "$skill" ]; then break; fi\n'
        'done\n'
        "# Read current status from handoff\n"
        'current=$(grep -m1 "^  - Status:" "$HANDOFF" | sed "s/^  - Status: *//")\n'
        'next=""\n'
        f'case "$current" in\n'
        f"{branches}\n"
        '  esac\n'
        'if [ -n "$next" ]; then\n'
        '  sed -i "s/^  - Status: .*/  - Status: $next/" "$HANDOFF"\n'
        '  echo "$skill" >> "$RECORD_FILE"\n'
        'fi\n'
        f"exit {exit_status}\n"
    )


def _run_runner(d: Path, approve: str = "", max_runs: str = "12", issue: str = "999") -> subprocess.CompletedProcess:
    env = os.environ | {
        "HANDOFF": str(d / f"{issue}-handoff.md"),
        "RECORD_FILE": str(d / "calls.log"),
    }
    if approve:
        env["APPROVE"] = approve
    return subprocess.run(
        [str(Path(__file__).resolve().parent.parent / "scripts" / "run-skill.sh"), issue],
        capture_output=True, text=True, env=env,
        cwd=str(d),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_full_pipeline():
    """created → designed → planned → implementing → implemented → shipped via design→fplan→implement→review→ship."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        plans = d / "plans"
        plans.mkdir()
        _write_handoff(plans, "created")
        (d / "calls.log").write_text("")

        transitions = {
            "created": "designed",
            "designed": "planned",
            "planned": "implementing",
            "implementing": "implemented",
            "implemented": "shipped",
        }
        (d / "claude").write_text(_fake_clude_factory(transitions))
        os.chmod(d / "claude", 0o755)

        env = os.environ | {
            "HANDOFF": str(plans / "999-handoff.md"),
            "RECORD_FILE": str(d / "calls.log"),
            "PATH": str(d) + ":" + os.environ["PATH"],
            "APPROVE": "1",
        }
        result = subprocess.run(
            [str(Path(__file__).resolve().parent.parent / "scripts" / "run-skill.sh"), "999"],
            capture_output=True, text=True, env=env,
            cwd=str(d),
        )

        assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
        assert "Workflow shipped" in result.stdout

        calls = (d / "calls.log").read_text().strip().split("\n")
        expected = ["design", "fplan", "implement", "review", "ship"]
        assert calls == expected, f"Got {calls!r}, expected {expected}"


def test_no_progress_stops():
    """Status unchanged after a skill run → exit 1."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        plans = d / "plans"
        plans.mkdir()
        _write_handoff(plans, "created")
        (d / "claude").write_text("#!/usr/bin/env bash\nexit 0\n")
        os.chmod(d / "claude", 0o755)

        env = os.environ | {
            "HANDOFF": str(plans / "999-handoff.md"),
            "RECORD_FILE": str(d / "calls.log"),
            "PATH": str(d) + ":" + os.environ["PATH"],
        }
        result = subprocess.run(
            [str(Path(__file__).resolve().parent.parent / "scripts" / "run-skill.sh"), "999"],
            capture_output=True, text=True, env=env,
            cwd=str(d),
        )

        assert result.returncode != 0
        assert "unchanged" in result.stderr or "WARNING" in result.stderr


def test_blocked_exits_nonzero():
    """Status=blocked → immediate exit 1."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        plans = d / "plans"
        plans.mkdir()
        _write_handoff(plans, "blocked")

        env = os.environ | {
            "HANDOFF": str(plans / "999-handoff.md"),
            "RECORD_FILE": str(d / "calls.log"),
        }
        result = subprocess.run(
            [str(Path(__file__).resolve().parent.parent / "scripts" / "run-skill.sh"), "999"],
            capture_output=True, text=True, env=env,
            cwd=str(d),
        )

        assert result.returncode != 0
        assert "blocked" in result.stderr


def test_max_runs_exceeded():
    """Status keeps changing but never reaches shipped → MAX_RUNS exit 1."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        plans = d / "plans"
        plans.mkdir()
        _write_handoff(plans, "created")
        (d / "calls.log").write_text("")

        # Infinite loop: created → designed → created → designed → ...
        transitions = {
            "created": "designed",
            "designed": "created",
        }
        (d / "claude").write_text(_fake_clude_factory(transitions))
        os.chmod(d / "claude", 0o755)

        env = os.environ | {
            "HANDOFF": str(plans / "999-handoff.md"),
            "RECORD_FILE": str(d / "calls.log"),
            "PATH": str(d) + ":" + os.environ["PATH"],
            "APPROVE": "1",
        }
        result = subprocess.run(
            [str(Path(__file__).resolve().parent.parent / "scripts" / "run-skill.sh"), "999"],
            capture_output=True, text=True, env=env,
            cwd=str(d),
        )

        assert result.returncode != 0
        assert "MAX_RUNS" in result.stderr


def test_missing_handoff():
    """No handoff file → exit 1 with error."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        env = os.environ | {"HANDOFF": str(d / "nope-handoff.md")}
        result = subprocess.run(
            [str(Path(__file__).resolve().parent.parent / "scripts" / "run-skill.sh"), "nope"],
            capture_output=True, text=True, env=env,
        )

        assert result.returncode != 0
        assert "handoff not found" in result.stderr


if __name__ == "__main__":
    for name, obj in list(globals().items()):
        if name.startswith("test_") and callable(obj):
            print(f"RUNNING {name}...", file=sys.stderr)
            obj()
            print(f"  OK", file=sys.stderr)
    print("All tests passed.", file=sys.stderr)
