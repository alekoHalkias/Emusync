"""Skill loader: discovers and loads skill instructions, injects context.

Skills are loaded from:
1. CLI's default skills directory: workflow-cli/skills/<skill>/SKILL.md
2. Project overrides: projects/<repo-id>/skills/<skill>/SKILL.md

Context injected into prompts:
- System prompt (generic action format rules)
- Skill instructions (SKILL.md content)
- Project rules (CLAUDE.md, GOTCHAS.md, etc.)
- Handoff context (current handoff file)
- Plan context (current plan file, if applicable)
- Code context (relevant file contents, requested by LLM)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from workflow_cli.config import _projects_dir


def _default_skills_dir() -> Path:
    """Return the CLI's default skills directory."""
    return Path(__file__).resolve().parent.parent / "skills"


def _project_skills_dir(project_id: str) -> Path:
    """Return the project's override skills directory."""
    return _projects_dir() / project_id / "skills"


def find_skill(skill_name: str, project_id: str | None = None) -> Path | None:
    """Find the SKILL.md file for a given skill.

    Searches project overrides first, then CLI defaults.
    Returns None if not found.
    """
    # Check project overrides first
    if project_id:
        project_path = _project_skills_dir(project_id) / skill_name / "SKILL.md"
        if project_path.is_file():
            return project_path

    # Fall back to CLI defaults
    default_path = _default_skills_dir() / skill_name / "SKILL.md"
    if default_path.is_file():
        return default_path

    return None


def load_skill(skill_name: str, project_id: str | None = None) -> str | None:
    """Load the full content of a skill's SKILL.md.

    Returns None if the skill is not found.
    """
    path = find_skill(skill_name, project_id)
    if path is None:
        return None
    return path.read_text()


def build_prompt(
    skill_name: str,
    system_prompt: str,
    project_rules: list[str],
    handoff_context: str,
    plan_context: str = "",
    code_context: list[dict[str, str]] | None = None,
    project_id: str | None = None,
) -> str:
    """Build a complete prompt for the LLM.

    Assembles: system prompt + skill instructions + project rules +
    handoff context + plan context + code context + action format reminder.
    """
    skill_content = load_skill(skill_name, project_id)
    if skill_content is None:
        raise ValueError(f"Skill not found: {skill_name}")

    parts = [
        system_prompt,
        "",
        "=== SKILL INSTRUCTIONS ===",
        skill_content,
        "",
    ]

    if project_rules:
        parts.extend([
            "=== PROJECT RULES ===",
            "\n\n".join(project_rules),
            "",
        ])

    parts.extend([
        "=== HANDOFF FILE ===",
        handoff_context,
        "",
    ])

    if plan_context:
        parts.extend([
            "=== PLAN FILE ===",
            plan_context,
            "",
        ])

    if code_context:
        parts.extend([
            "=== CODE CONTEXT ===",
        ])
        for item in code_context:
            parts.extend([
                f"\n--- {item['path']} ---",
                item["content"],
                "",
            ])

    parts.extend([
        "=== ACTION FORMAT ===",
        "Return JSON with this structure:",
        '{',
        '  "skill": "<skill_name>",',
        '  "turn": <number>,',
        '  "actions": [',
        '    {"id": "a1", "type": "bash", "params": {"command": "..."}},',
        "  ],",
        '  "output": null,',
        '  "needs_user_input": false',
        "}",
        "",
        "Available action types: bash, gh, read, write, edit, ask_user, approve, skip, error",
        "",
        "Execute actions in order. When all actions are done and the skill is complete,",
        'set "actions": [] and include your output in the "output" field.',
        'Set "stage_complete": true and "next_skill": "<skill_name>" when done.',
    ])

    return "\n".join(parts)


def load_project_rules(project_id: str, rule_files: list[str]) -> list[str]:
    """Load the content of project rule files.

    Rule files are expected to be in the target repository.
    This function reads them from the repo path stored in the project config.
    Returns a list of file contents (one per rule file found).
    """
    contents = []
    # The actual repo path would be stored in the project config.
    # For now, this is a placeholder that would be called with the repo root.
    return contents
