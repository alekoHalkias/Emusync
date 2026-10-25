"""Stage router: determines the next skill based on handoff file status.

Valid transitions:
  created -> designed -> planned -> implementing -> implemented -> shipped
  implemented -> blocked (on failure)
  planned -> blocked (on failure)
"""

from __future__ import annotations

import re
from typing import Optional

# Valid status transitions
VALID_TRANSITIONS = {
    "created": "designed",
    "designed": "planned",
    "planned": "implementing",
    "implementing": "implemented",
    "implemented": "shipped",
    "implemented": "blocked",
    "planned": "blocked",
}

# Skill to invoke for each status
SKILL_MAP = {
    "created": "issue",
    "designed": "design",
    "planned": "bplan",  # or fplan, or both (depends on Plan target)
    "implementing": "implement",
    "implemented": "ship",
    "shipped": None,  # done
    "blocked": None,  # stop, show failure report
}

# Skills that may need sub-skills
COMPOUND_SKILLS = {
    "planned": ["bplan", "fplan", "merge"],  # depends on Plan target from design
}


def parse_status(handoff_text: str) -> Optional[str]:
    """Extract the Status field from a handoff file."""
    m = re.search(r"^- Status:\s*(\S+)", handoff_text, re.M)
    return m.group(1) if m else None


def next_skill(handoff_text: str) -> Optional[str]:
    """Determine the next skill to invoke based on handoff status.

    Returns the skill name, or None if the workflow is complete/blocked.
    Raises ValueError if the status is unknown.
    """
    status = parse_status(handoff_text)
    if status is None:
        return "issue"  # No status found, start from issue

    if status not in SKILL_MAP:
        raise ValueError(f"Unknown status: {status}")

    return SKILL_MAP.get(status)


def validate_transition(current: str, target: str) -> bool:
    """Check if a status transition is valid."""
    if current == target:
        return True  # No transition needed
    return VALID_TRANSITIONS.get(current) == target


def is_terminal(status: str) -> bool:
    """Check if the status is a terminal state (shipped or blocked)."""
    return status in ("shipped", "blocked")


def needs_plan_target(handoff_text: str) -> Optional[str]:
    """Check if the handoff has a Plan target set (from design stage).

    Returns 'bplan', 'fplan', or 'both', or None if not set.
    """
    m = re.search(r"### Plan Target:\s*(\S+)", handoff_text)
    if m:
        return m.group(1)
    return None
