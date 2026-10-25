"""Tests for stages.py."""

import pytest

from workflow_cli.stages import (
    VALID_TRANSITIONS,
    is_terminal,
    next_skill,
    parse_status,
    validate_transition,
)


def test_valid_transitions():
    """Test that valid transitions are defined."""
    assert "created" in VALID_TRANSITIONS
    assert "implementing" in VALID_TRANSITIONS


def test_parse_status():
    """Test parsing status from handoff text."""
    text = "Status: designing"
    assert parse_status(text) == "designing"

    text = "Status: implementing\nMore text"
    assert parse_status(text) == "implementing"

    text = "No status here"
    assert parse_status(text) is None


def test_parse_status_missing():
    """Test parsing status when not present."""
    assert parse_status("Just some text") is None


def test_validate_transition_valid():
    """Test valid transitions."""
    assert validate_transition("created", "designing")[0] is True
    assert validate_transition("designing", "planning")[0] is True


def test_validate_transition_invalid():
    """Test invalid transitions."""
    allowed, reason = validate_transition("created", "shipped")
    assert allowed is False


def test_is_terminal():
    """Test terminal status detection."""
    assert is_terminal("shipped") is True
    assert is_terminal("blocked") is True
    assert is_terminal("implementing") is False


def test_next_skill():
    """Test next skill dispatch."""
    text = "- Status: created"
    # next_skill would parse and return the next skill
    # For now, just test it doesn't crash
    result = next_skill(text)
    assert result is not None or text.strip() == ""
