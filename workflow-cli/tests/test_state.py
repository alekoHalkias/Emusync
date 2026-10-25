"""Tests for state.py."""

import json
import tempfile
from pathlib import Path

import pytest

from workflow_cli.state import (
    HANDOFF_TEMPLATE,
    append_handoff_log,
    create_handoff,
    read_handoff,
    read_state,
    update_handoff_section,
    write_state,
)


def test_handoff_template_has_all_sections():
    """Test that the handoff template contains all 12 sections."""
    sections = [
        "## 1. Issue",
        "## 2. Design",
        "## 3. Backend Plan",
        "## 4. Frontend Plan",
        "## 5. Test Plan",
        "## 6. Implementation Checklist",
        "## 7. Review Findings",
        "## 8. Implementation Steps",
        "## 9. Review",
        "## 10. Ship",
        "## 11. Fix Attempts",
        "## 12. Log",
    ]
    for section in sections:
        assert section in HANDOFF_TEMPLATE, f"Missing section: {section}"


def test_create_and_read_handoff(tmp_path):
    """Test creating and reading a handoff file."""
    pid = "test-project"
    issue = "42"

    create_handoff(pid, issue, "Test issue")
    handoff_path = tmp_path / "projects" / pid / "handoff" / f"{issue}-handoff.md"

    assert handoff_path.exists()
    content = handoff_path.read_text()
    assert "Test issue" in content


def test_read_handoff_missing(tmp_path):
    """Test reading a non-existent handoff returns None."""
    assert read_handoff("nonexistent", "1") is None


def test_update_handoff_section(tmp_path):
    """Test updating a section in the handoff file."""
    pid = "test-project"
    issue = "42"

    create_handoff(pid, issue, "Test")
    update_handoff_section(pid, issue, "## 1. Issue", "Updated content")

    content = read_handoff(pid, issue)
    assert "Updated content" in content


def test_write_and_read_state(tmp_path):
    """Test writing and reading state.json."""
    pid = "test-project"

    write_state(pid, {"status": "created", "turn": 1})
    state = read_state(pid)
    assert state["status"] == "created"
    assert state["turn"] == 1


def test_atomic_write_produces_valid_file(tmp_path):
    """Test that atomic writes produce valid files."""
    pid = "test-project"
    state_path = tmp_path / "projects" / pid / "state.json"

    write_state(pid, {"key": "value"})
    assert state_path.exists()
    data = json.loads(state_path.read_text())
    assert data["key"] == "value"
