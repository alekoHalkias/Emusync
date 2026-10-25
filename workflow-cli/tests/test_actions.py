"""Tests for actions.py."""

import pytest

from workflow_cli.actions import execute_action, execute_actions


def test_bash_action_success():
    """Test bash action with a successful command."""
    result = execute_action({"type": "bash", "params": {"command": "echo hello"}})
    assert result["ok"] is True
    assert result["exit_code"] == 0
    assert "hello" in result["stdout"]


def test_bash_action_failure():
    """Test bash action with a failing command."""
    result = execute_action({"type": "bash", "params": {"command": "exit 1"}})
    assert result["ok"] is False
    assert result["exit_code"] == 1


def test_read_action_file_not_found():
    """Test read action with non-existent file."""
    result = execute_action({"type": "read", "params": {"path": "/nonexistent/file.txt"}})
    assert result["ok"] is False
    assert "not found" in result["error"].lower()


def test_write_action(tmp_path):
    """Test write action creates file."""
    path = str(tmp_path / "test.txt")
    result = execute_action({"type": "write", "params": {"path": path, "content": "hello"}})
    assert result["ok"] is True
    assert (tmp_path / "test.txt").read_text() == "hello"


def test_edit_action(tmp_path):
    """Test edit action replaces text."""
    path = str(tmp_path / "test.txt")
    (tmp_path / "test.txt").write_text("hello world")

    result = execute_action({
        "type": "edit",
        "params": {"path": path, "old_string": "world", "new_string": "universe"},
    })
    assert result["ok"] is True
    assert (tmp_path / "test.txt").read_text() == "hello universe"


def test_edit_action_not_found(tmp_path):
    """Test edit action with non-matching old_string."""
    path = str(tmp_path / "test.txt")
    (tmp_path / "test.txt").write_text("hello")

    result = execute_action({
        "type": "edit",
        "params": {"path": path, "old_string": "world", "new_string": "universe"},
    })
    assert result["ok"] is False


def test_unknown_action_type():
    """Test unknown action type returns error."""
    result = execute_action({"type": "unknown", "params": {}})
    assert result["ok"] is False
    assert "unknown" in result["error"].lower()


def test_execute_actions_stops_on_error():
    """Test that execute_actions stops on error type."""
    actions = [
        {"type": "bash", "params": {"command": "echo 1"}},
        {"type": "error", "params": {"message": "stop"}},
        {"type": "bash", "params": {"command": "echo 2"}},
    ]
    results = execute_actions(actions)
    assert len(results) == 2  # Third action not executed
