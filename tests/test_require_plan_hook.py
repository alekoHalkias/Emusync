"""The .claude/hooks/require_plan.py edit gate (#586)."""
import importlib.util
import pathlib
import subprocess

_HOOK = pathlib.Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "require_plan.py"
_spec = importlib.util.spec_from_file_location("require_plan", _HOOK)
require_plan = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(require_plan)


def _repo(tmp_path, branch):
    subprocess.run(["git", "init", "-q", "-b", branch, str(tmp_path)], check=True)
    return tmp_path


def _check(repo, rel):
    return require_plan.check({"cwd": str(repo), "tool_input": {"file_path": str(repo / rel)}})


def test_blocks_code_on_unlinked_branch(tmp_path):
    repo = _repo(tmp_path, "main")
    assert "not linked" in _check(repo, "server/x.py")


def test_allows_plans_and_claude_dirs(tmp_path):
    repo = _repo(tmp_path, "main")
    assert _check(repo, "plans/5-x.md") is None
    assert _check(repo, ".claude/skills/plan/SKILL.md") is None


def test_allows_paths_outside_repo(tmp_path):
    repo = _repo(tmp_path / "r", "main")
    assert require_plan.check({"cwd": str(repo), "tool_input": {"file_path": str(tmp_path / "elsewhere.txt")}}) is None


def test_requires_plan_file_then_implementing_status(tmp_path):
    repo = _repo(tmp_path, "feature/5-thing")
    assert "Run /plan 5" in _check(repo, "server/x.py")
    (repo / "plans").mkdir()
    plan = repo / "plans" / "5-thing.md"
    plan.write_text("Status: planned\n")
    assert "Status: planned" in _check(repo, "server/x.py")
    plan.write_text("Status: implementing\n")
    assert _check(repo, "server/x.py") is None
