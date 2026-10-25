"""Tests for progress.py."""

import pytest

from workflow_cli.progress import STAGE_PREFIXES, stage_prefix


def test_stage_prefix_known():
    """Test prefix for known stage."""
    color, prefix = stage_prefix("created")
    assert color == "blue"
    assert prefix == "[ISSUE]"


def test_stage_prefix_unknown():
    """Test prefix for unknown stage defaults."""
    color, prefix = stage_prefix("unknown_stage")
    assert color == "white"
    assert prefix == "[WORKFLOW]"


def test_stage_prefixes_complete():
    """Test that all expected stages have prefixes."""
    expected = ["created", "design", "implementing", "shipped", "blocked"]
    for stage in expected:
        assert stage in STAGE_PREFIXES
