"""The .claude/hooks/require_plan.py edit gate (#586)."""
import importlib.util
import pathlib

_HOOK = pathlib.Path(__file__).resolve().parent.parent.parent / ".claude" / "hooks" / "require_plan.py"
_spec = importlib.util.spec_from_file_location("require_plan", _HOOK)
require_plan = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(require_plan)


def _repo(tmp_path, branch):
    tmp_path.mkdir(parents=True, exist_ok=True)
    require_plan.git(str(tmp_path), "init", "-q", "-b", branch)  # env-clean: pre-push sets GIT_DIR
    return tmp_path


def _check(repo, rel):
    return require_plan.check({"cwd": str(repo), "tool_input": {"file_path": str(repo / rel)}})


def test_blocks_code_on_unlinked_branch(tmp_path):
    repo = _repo(tmp_path, "main")
    assert "not linked" in _check(repo, "src/server/x.py")


def test_allows_plans_and_claude_dirs(tmp_path):
    repo = _repo(tmp_path, "main")
    assert _check(repo, "tools/plans/5-x.md") is None
    assert _check(repo, ".claude/skills/plan/SKILL.md") is None


def test_allows_paths_outside_repo(tmp_path):
    repo = _repo(tmp_path / "r", "main")
    assert require_plan.check({"cwd": str(repo), "tool_input": {"file_path": str(tmp_path / "elsewhere.txt")}}) is None


def test_requires_plan_file_then_implementing_status(tmp_path):
    repo = _repo(tmp_path, "feature/5-thing")
    assert "Run /plan 5" in _check(repo, "server/x.py")
    (repo / "tools" / "plans").mkdir(parents=True)
    plan = repo / "tools" / "plans" / "5-thing.md"
    plan.write_text("Status: planned\n")
    assert "Status: planned" in _check(repo, "server/x.py")
    plan.write_text("Status: implementing\n")
    assert _check(repo, "server/x.py") is None
