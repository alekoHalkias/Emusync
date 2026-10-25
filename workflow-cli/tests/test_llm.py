"""Tests for llm.py."""

import json

import pytest
import httpx

from workflow_cli.llm import LLMClient


def test_parse_response_plain():
    """Test parsing plain JSON response."""
    client = LLMClient()
    content = '{"skill": "test", "turn": 1, "actions": []}'
    result = client._parse_response(content)
    assert result["skill"] == "test"
    assert result["turn"] == 1


def test_parse_response_with_fences():
    """Test parsing JSON wrapped in markdown fences."""
    client = LLMClient()
    content = '```json\n{"skill": "test", "turn": 1}\n```'
    result = client._parse_response(content)
    assert result["skill"] == "test"


def test_parse_response_invalid_json():
    """Test parsing invalid JSON returns raw content."""
    client = LLMClient()
    content = "not json at all"
    result = client._parse_response(content)
    assert result["_parse_failed"] is True
    assert result["_raw"] == content


def test_url_building():
    """Test URL building from path segments."""
    client = LLMClient(base_url="http://localhost:8080")
    assert client._url("/v1/chat") == "http://localhost:8080/v1/chat"
    assert client._url("v1/chat") == "http://localhost:8080/v1/chat"


def test_health_returns_false_on_failure():
    """Test health check returns False when endpoint is down."""
    client = LLMClient(base_url="http://localhost:1")
    assert client.health() is False
