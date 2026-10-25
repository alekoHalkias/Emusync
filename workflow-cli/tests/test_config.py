"""Tests for config.py."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from workflow_cli.config import (
    HooksConfig,
    LlamaSwapConfig,
    ProjectConfig,
    ProjectSettings,
    RepoInfo,
    _projects_dir,
    discover_repo,
    load_project_config,
    register_project,
    save_project_config,
)


@pytest.fixture
def tmp_project_dir(tmp_path):
    """Create a temporary projects directory."""
    return tmp_path


def test_register_project(tmp_project_dir):
    """Test registering a new project."""
    # Patch _projects_dir to use tmp_path
    import workflow_cli.config as config_mod
    original = config_mod._PROJECTS_DIR

    try:
        config_mod._PROJECTS_DIR = tmp_project_dir

        repo_path = str(tmp_project_dir / "test-repo")
        os.makedirs(repo_path)
        Path(repo_path, ".git").mkdir()

        pid = register_project(repo_path, "test-repo")
        assert pid == "test-repo"

        config = load_project_config("test-repo")
        assert config is not None
        assert config.name == "test-repo"
        assert config.repo_path == repo_path
    finally:
        config_mod._PROJECTS_DIR = original


def test_load_project_config_not_found(tmp_project_dir):
    """Test loading a non-existent project returns None."""
    import workflow_cli.config as config_mod
    original = config_mod._PROJECTS_DIR
    try:
        config_mod._PROJECTS_DIR = tmp_project_dir
        assert load_project_config("nonexistent") is None
    finally:
        config_mod._PROJECTS_DIR = original


def test_save_and_load_config(tmp_project_dir):
    """Test saving and loading config with atomic write."""
    import workflow_cli.config as config_mod
    original = config_mod._PROJECTS_DIR
    try:
        config_mod._PROJECTS_DIR = tmp_project_dir
        repo_path = str(tmp_project_dir / "test-repo")
        os.makedirs(repo_path)
        Path(repo_path, ".git").mkdir()

        register_project(repo_path, "test-repo")
        config = load_project_config("test-repo")
        assert config is not None

        # Update settings
        config.settings.default_branch = "develop"
        save_project_config("test-repo", config.settings)

        # Reload and verify
        config2 = load_project_config("test-repo")
        assert config2.settings.default_branch == "develop"
    finally:
        config_mod._PROJECTS_DIR = original


def test_llama_swap_config_defaults():
    """Test LlamaSwapConfig default values."""
    cfg = LlamaSwapConfig()
    assert cfg.base_url == "http://localhost:8080"
    assert cfg.model == "claude-sonnet-4-20250514"
    assert cfg.timeout == 300
    assert cfg.max_retries == 3


def test_hooks_config_defaults():
    """Test HooksConfig default values."""
    cfg = HooksConfig()
    assert cfg.server_sync is None
    assert cfg.doc_sync is None
    assert cfg.pre_ship is None


def test_discover_repo_no_rule_files(tmp_path):
    """Test repo discovery with no rule files."""
    repo_path = str(tmp_path / "repo")
    os.makedirs(repo_path)
    Path(repo_path, ".git").mkdir()

    info = discover_repo(repo_path)
    assert info is not None
    assert info.name == "repo"
    assert len(info.rule_files) == 0
