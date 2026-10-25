"""Gate logic: plan approval, ship approval, revision feedback loop.

Handles the approval/revision flow between stages. When a gate requires
user input, it returns an ask_user action. When a revision is needed,
it formats feedback for the LLM.
"""

from __future__ import annotations

import logging

from workflow_cli.progress import console, print_approval_request, Text

logger = logging.getLogger(__name__)

# Gates that require approval
APPROVAL_GATES = {
    "plan": "Do you approve this plan?",
    "ship": "Do you approve shipping this change?",
}


def gate_decision(gate_name: str, summary: str) -> str | None:
    """Present a gate summary and prompt for a decision.

    Returns the user's decision ('approve', 'revise', 'reject') or None
    if the user cancelled.
    """
    question = APPROVAL_GATES.get(gate_name, "Approve this change?")

    print_approval_request(question, ["approve", "revise", "reject"])
    # In the actual runtime, this would call the ask_user action
    # For now, return a placeholder — the runtime handles the actual prompt
    return None  # Signals that user input is needed


def format_revision_feedback(gate_name: str, feedback: str) -> str:
    """Format revision feedback for the LLM.

    When a gate is rejected or revised, this formats the feedback
    into a prompt the LLM can act on.
    """
    return (
        f"REVISION REQUESTED on gate: {gate_name}\n\n"
        f"Feedback:\n{feedback}\n\n"
        "Please revise your work based on this feedback and re-submit."
    )


def format_approval_summary(gate_name: str, content: str) -> str:
    """Format a summary for an approval gate.

    Returns a string suitable for display to the user before approval.
    """
    return f"=== {gate_name.upper()} GATE ===\n\n{content}"


def needs_approval(status: str) -> bool:
    """Check if a stage transition requires user approval.

    Plan approval: before transitioning from 'planned' to 'implementing'.
    Ship approval: before transitioning from 'implemented' to 'shipped'.
    """
    return status in ("planned", "implemented")


def validate_transition(current: str, target: str, approved: dict[str, bool]) -> tuple[bool, str]:
    """Validate a stage transition with gate checks.

    Args:
        current: Current status.
        target: Target status.
        approved: Dict of which gates have been approved.

    Returns:
        (allowed, reason) tuple.
    """
    # Check if a gate is required
    if current == "planned" and target == "implementing":
        if not approved.get("plan"):
            return False, "Plan approval required before implementing"
        return True, "Plan approved"

    if current == "implemented" and target == "shipped":
        if not approved.get("ship"):
            return False, "Ship approval required before shipping"
        return True, "Ship approved"

    # No gate required for this transition
    return True, "No gate required"
