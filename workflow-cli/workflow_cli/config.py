"""Project configuration loading and repository discovery.

Reads .workflow-cli/config.yaml from the CLI's projects directory.
Provides repo discovery on init: scans a target repo for rule files,
tech stack, test/lint commands, and git info.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ProjectConfig(BaseModel):
    """Project identification and settings."""

    name: str = Field(description="Human-readable project name")
    repo: str = Field(description="GitHub repo slug (owner/name)")
    remote: str = Field(default="origin", description="Git remote name")
    default_branch: str = Field(default="main", description="Default branch name")
    branch_prefix: str = Field(default="feature", description="Branch prefix for feature branches")


class LlamaSwapConfig(BaseModel):
    """LLM endpoint configuration."""

    url: str = Field(default="http://localhost:8080", description="llama-swap HTTP endpoint")
    model: str = Field(
        default="Qwen2.5-Coder-32B-Instruct.Q4_K_S.gguf",
        description="Model name to use",
    )


class HooksConfig(BaseModel):
    """Project-specific hooks."""

    server_sync: dict[str, Any] = field(default_factory=dict)
    doc_sync: dict[str, Any] = field(default_factory=dict)
    pre_ship: list[dict[str, str]] = field(default_factory=list)


class ProjectSettings(BaseModel):
    """Full project configuration."""

    project: ProjectConfig
    llama_swap: LlamaSwapConfig = Field(default_factory=LlamaSwapConfig)
    skills_dir: str = Field(default=".claude/skills", description="Path to skill definitions")
    rule_files: list[str] = Field(
        default_factory=lambda: ["CLAUDE.md", "docs/GOTCHAS.md", "docs/ARCHITECTURE.md"],
    )
    handoff_path: str = Field(
        default="plans/{N}-handoff.md",
        description="Handoff file path template",
    )
    plan_path: str = Field(
        default="plans/{N}-{slug}.md",
        description="Plan file path template",
    )
    test_commands: list[str] = Field(default_factory=lambda: ["make test-changed"])
    lint_commands: dict[str, str] = field(default_factory=dict)
    hooks: HooksConfig = Field(default_factory=HooksConfig)


# ---------------------------------------------------------------------------
# Repo discovery
# ---------------------------------------------------------------------------

@dataclass
class RepoInfo:
    """Information discovered from scanning a target repository."""

    root: Path
    name: str
    rule_files: list[str] = field(default_factory=list)
    tech_stack: dict[str, str] = field(default_factory=dict)
    test_commands: list[str] = field(default_factory=list)
    lint_commands: dict[str, str] = field(default_factory=dict)
    remote_url: str = ""
    default_branch: str = "main"


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a command and return the result."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env)


def discover_repo(repo_path: str) -> RepoInfo:
    """Scan a target repository and return discovered information.

    Looks for:
    - Rule files (CLAUDE.md, CONTRIBUTING.md, docs/ARCHITECTURE.md, etc.)
    - Tech stack (package.json, pyproject.toml, Makefile, etc.)
    - Test/lint commands from Makefile, package.json, pyproject.toml
    - Git info (remote URL, default branch)
    """
    root = Path(repo_path).resolve()
    if not (root / ".git").exists():
        raise ValueError(f"Not a git repository: {root} (no .git directory)")

    info = RepoInfo(root=root, name=root.name)

    # Git info
    rem = _run(["git", "remote", "get-url", "origin"], root)
    if rem.returncode == 0:
        url = rem.stdout.strip()
        # Convert SSH URL to owner/name format
        m = re.search(r"[:/]([^/]+)/([^/.]+)(?:\.git)?$", url)
        if m:
            info.remote_url = f"{m.group(1)}/{m.group(2)}"
    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], root)
    if branch.returncode == 0:
        info.default_branch = branch.stdout.strip()

    # Rule files
    rule_candidates = [
        "CLAUDE.md",
        "CONTRIBUTING.md",
        "docs/ARCHITECTURE.md",
        "docs/GOTCHAS.md",
        "README.md",
        "ARCHITECTURE.md",
        "GOTCHAS.md",
    ]
    for candidate in rule_candidates:
        if (root / candidate).is_file():
            info.rule_files.append(candidate)

    # Tech stack detection
    if (root / "package.json").is_file():
        info.tech_stack["frontend"] = "typescript"
        info.tech_stack["runtime"] = "node"
    if (root / "pyproject.toml").is_file() or (root / "setup.py").is_file():
        info.tech_stack["backend"] = "python"
    if (root / "Makefile").is_file():
        info.tech_stack["build_system"] = "make"

    # Test commands from Makefile
    makefile = root / "Makefile"
    if makefile.is_file():
        content = makefile.read_text()
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("test") and ":" in line:
                cmd = line.split(":", 1)[1].strip()
                if cmd:
                    info.test_commands.append(cmd)
        if not info.test_commands:
            info.test_commands = ["make test"]

    # Test commands from package.json
    pkg_json = root / "package.json"
    if pkg_json.is_file():
        try:
            import json as _json

            pkg = _json.loads(pkg_json.read_text())
            scripts = pkg.get("scripts", {})
            if "test" in scripts:
                info.test_commands.append(f"npm test")
            if "lint" in scripts:
                info.lint_commands["typescript"] = f"npm run {scripts['lint']}"
        except Exception:
            pass

    # Lint commands from pyproject.toml
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            import tomllib

            with open(pyproject, "rb") as f:
                data = tomllib.load(f)
            # Check for lint/test tool configs
        except Exception:
            pass

    if not info.test_commands:
        info.test_commands = ["make test"]

    return info


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def _projects_dir() -> Path:
    """Return the CLI's projects directory."""
    return Path(__file__).resolve().parent.parent / "projects"


def _project_config_path(project_id: str) -> Path:
    """Return the config path for a given project."""
    return _projects_dir() / project_id / "config.yaml"


def load_project_config(project_id: str) -> ProjectSettings | None:
    """Load project config from the CLI's projects directory.

    Returns None if the config file doesn't exist or is corrupt.
    """
    path = _project_config_path(project_id)
    if not path.is_file():
        return None
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            return None
        return ProjectSettings(**data)
    except Exception:
        return None


def save_project_config(project_id: str, settings: ProjectSettings) -> Path:
    """Save project config atomically to the CLI's projects directory."""
    proj_dir = _projects_dir() / project_id
    proj_dir.mkdir(parents=True, exist_ok=True)
    path = _project_config_path(project_id)

    # Write to temp file first, then rename (atomic)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        yaml.dump(settings.model_dump(mode="json"), f, default_flow_style=False)
    tmp.rename(path)
    os.chmod(path, 0o600)
    return path


def register_project(repo_path: str, name: str | None = None) -> str:
    """Register a new project by scanning it and saving config.

    Returns the project ID (owner-repo slug).
    """
    info = discover_repo(repo_path)

    if name is None:
        name = info.name

    # Infer repo slug from remote URL if available
    repo_slug = info.remote_url if info.remote_url else f"unknown/{name}"

    settings = ProjectSettings(
        project=ProjectConfig(
            name=name,
            repo=repo_slug,
            default_branch=info.default_branch,
        ),
        rule_files=info.rule_files,
        test_commands=info.test_commands,
        lint_commands=info.lint_commands,
    )

    project_id = repo_slug.replace("/", "-").replace(".", "-").lower()
    path = save_project_config(project_id, settings)

    return project_id
