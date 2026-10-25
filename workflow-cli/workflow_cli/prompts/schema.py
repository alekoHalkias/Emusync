"""JSON schema for validating LLM responses.

Uses pydantic to validate the structure of LLM output before execution.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ActionParam(BaseModel):
    """Base model for action parameters."""
    pass


class BashParams(ActionParam):
    command: str
    timeout: int = 300
    cwd: str | None = None


class GhParams(ActionParam):
    command: str
    timeout: int = 60


class ReadParams(ActionParam):
    path: str
    max_lines: int = 500


class WriteParams(ActionParam):
    path: str
    content: str


class EditParams(ActionParam):
    path: str
    old_string: str
    new_string: str
    replace_all: bool = False


class AskUserParams(ActionParam):
    question: str
    options: list[str] = Field(default_factory=list)
    multi_select: bool = False


class ApproveParams(ActionParam):
    decision: str = Field(pattern="^(approve|revise|reject)$")
    feedback: str = ""


class SkipParams(ActionParam):
    reason: str = ""


class ErrorParams(ActionParam):
    message: str


# Union type for all action param types
ActionParams = BashParams | GhParams | ReadParams | WriteParams | EditParams | AskUserParams | ApproveParams | SkipParams | ErrorParams


class Action(BaseModel):
    """A single action in a batch."""
    id: str
    type: str = Field(pattern="^(bash|gh|read|write|edit|ask_user|approve|skip|error)$")
    params: dict[str, Any] = Field(default_factory=dict)


class LLMResponse(BaseModel):
    """The complete LLM response structure."""
    skill: str
    turn: int = Field(ge=1)
    actions: list[Action] = Field(default_factory=list)
    output: str | None = None
    needs_user_input: bool = False
    stage_complete: bool = False
    next_skill: str | None = None


def validate_response(data: dict[str, Any]) -> LLMResponse | None:
    """Validate an LLM response against the schema.

    Returns the validated response, or None if validation fails.
    """
    try:
        return LLMResponse(**data)
    except Exception as e:
        print(f"Validation error: {e}")
        return None
