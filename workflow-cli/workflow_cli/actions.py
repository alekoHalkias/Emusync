"""Action executor: dispatches typed actions (bash, gh, read, write, edit, ask_user, approve, skip, error).

Each action type has its own handler. Results are collected and returned
as a dict with stdout, stderr, exit_code (for bash/gh) or path/status (for file ops).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

from workflow_cli.config import _projects_dir

logger = logging.getLogger(__name__)

# Action result types
ActionResult = dict[str, Any]


def _bash_action(params: dict[str, Any]) -> ActionResult:
    """Execute a shell command and return the result."""
    command = params.get("command", "")
    timeout = params.get("timeout", 300)
    cwd = params.get("cwd")

    logger.info("bash: %s", command[:100])

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        return {
            "type": "bash",
            "exit_code": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "ok": result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {
            "type": "bash",
            "exit_code": -1,
            "stdout": "",
            "stderr": f"Command timed out after {timeout}s",
            "ok": False,
        }
    except Exception as e:
        return {
            "type": "bash",
            "exit_code": -1,
            "stdout": "",
            "stderr": str(e),
            "ok": False,
        }


def _gh_action(params: dict[str, Any]) -> ActionResult:
    """Execute a gh CLI command and return the result."""
    # gh commands should be passed as a list, not shell string
    command = ["gh", *params.get("command", "").split()]
    timeout = params.get("timeout", 60)

    logger.info("gh: %s", " ".join(command))

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout.strip()
        # Try to parse JSON if it looks like JSON
        try:
            parsed = json.loads(output) if output else None
        except json.JSONDecodeError:
            parsed = None
        return {
            "type": "gh",
            "exit_code": result.returncode,
            "stdout": output,
            "stderr": result.stderr.strip(),
            "ok": result.returncode == 0,
            "parsed": parsed,
        }
    except subprocess.TimeoutExpired:
        return {
            "type": "gh",
            "exit_code": -1,
            "stdout": "",
            "stderr": f"Command timed out after {timeout}s",
            "ok": False,
        }
    except FileNotFoundError:
        return {
            "type": "gh",
            "exit_code": -1,
            "stdout": "",
            "stderr": "gh CLI not found",
            "ok": False,
        }
    except Exception as e:
        return {
            "type": "gh",
            "exit_code": -1,
            "stdout": "",
            "stderr": str(e),
            "ok": False,
        }


def _read_action(params: dict[str, Any]) -> ActionResult:
    """Read a file and return its contents."""
    path = params.get("path", "")
    max_lines = params.get("max_lines", 500)

    logger.info("read: %s", path)

    try:
        full_path = Path(path)
        if not full_path.is_file():
            return {
                "type": "read",
                "ok": False,
                "error": f"File not found: {path}",
            }
        content = full_path.read_text()
        lines = content.split("\n")
        if len(lines) > max_lines:
            content = "\n".join(lines[:max_lines]) + f"\n... (truncated, {len(lines)} total lines)"
        return {
            "type": "read",
            "ok": True,
            "path": path,
            "content": content,
            "lines": len(lines),
        }
    except Exception as e:
        return {
            "type": "read",
            "ok": False,
            "error": str(e),
        }


def _write_action(params: dict[str, Any]) -> ActionResult:
    """Write content to a file atomically."""
    path = params.get("path", "")
    content = params.get("content", "")

    logger.info("write: %s (%d bytes)", path, len(content))

    try:
        full_path = Path(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write: write to temp file, then rename
        tmp_path = full_path.with_suffix(full_path.suffix + ".tmp")
        tmp_path.write_text(content)
        tmp_path.rename(full_path)

        # Set permissions
        os.chmod(full_path, 0o644)

        return {
            "type": "write",
            "ok": True,
            "path": path,
        }
    except Exception as e:
        return {
            "type": "write",
            "ok": False,
            "error": str(e),
        }


def _edit_action(params: dict[str, Any]) -> ActionResult:
    """Perform an exact string replacement in a file."""
    path = params.get("path", "")
    old_string = params.get("old_string", "")
    new_string = params.get("new_string", "")
    replace_all = params.get("replace_all", False)

    logger.info("edit: %s (%s replacement)", path, "all" if replace_all else "single")

    try:
        full_path = Path(path)
        if not full_path.is_file():
            return {
                "type": "edit",
                "ok": False,
                "error": f"File not found: {path}",
            }

        content = full_path.read_text()

        if old_string not in content:
            # Try to find similar strings for error context
            return {
                "type": "edit",
                "ok": False,
                "error": f"old_string not found in {path}",
                "content_length": len(content),
            }

        if replace_all:
            new_content = content.replace(old_string, new_string)
        else:
            new_content = content.replace(old_string, new_string, 1)

        # Atomic write
        tmp_path = full_path.with_suffix(full_path.suffix + ".tmp")
        tmp_path.write_text(new_content)
        tmp_path.rename(full_path)

        return {
            "type": "edit",
            "ok": True,
            "path": path,
            "replacements": new_content.count(new_string) if replace_all else 1,
        }
    except Exception as e:
        return {
            "type": "edit",
            "ok": False,
            "error": str(e),
        }


def _ask_user_action(params: dict[str, Any]) -> ActionResult:
    """Return an action for the runtime to prompt the user.

    This doesn't execute directly — it signals the runtime to present
    a question and wait for an answer.
    """
    return {
        "type": "ask_user",
        "ok": True,
        "question": params.get("question", ""),
        "options": params.get("options", []),
        "multi_select": params.get("multi_select", False),
    }


def _approve_action(params: dict[str, Any]) -> ActionResult:
    """Signal that user approval has been received."""
    return {
        "type": "approve",
        "ok": True,
        "decision": params.get("decision", "approve"),
        "feedback": params.get("feedback", ""),
    }


def _skip_action(params: dict[str, Any]) -> ActionResult:
    """Signal that a step/action should be skipped."""
    return {
        "type": "skip",
        "ok": True,
        "reason": params.get("reason", ""),
    }


def _error_action(params: dict[str, Any]) -> ActionResult:
    """Signal an error condition."""
    return {
        "type": "error",
        "ok": False,
        "message": params.get("message", "Unknown error"),
    }


# Action dispatch table
_ACTION_HANDLERS = {
    "bash": _bash_action,
    "gh": _gh_action,
    "read": _read_action,
    "write": _write_action,
    "edit": _edit_action,
    "ask_user": _ask_user_action,
    "approve": _approve_action,
    "skip": _skip_action,
    "error": _error_action,
}


def execute_action(action: dict[str, Any]) -> ActionResult:
    """Execute a single action and return the result.

    Args:
        action: Dict with "type" and "params" keys.

    Returns:
        ActionResult dict with execution results.
    """
    action_type = action.get("type", "")
    params = action.get("params", {})

    handler = _ACTION_HANDLERS.get(action_type)
    if handler is None:
        return {
            "type": action_type,
            "ok": False,
            "error": f"Unknown action type: {action_type}",
        }

    try:
        return handler(params)
    except Exception as e:
        logger.exception("Action %s failed: %s", action_type, e)
        return {
            "type": action_type,
            "ok": False,
            "error": str(e),
        }


def execute_actions(actions: list[dict[str, Any]]) -> list[ActionResult]:
    """Execute a batch of actions and return results in order.

    Stops on the first error action (type=error) or skip.
    """
    results = []
    for action in actions:
        result = execute_action(action)
        results.append(result)
        # Stop on error/skip actions
        if result.get("type") == "error" or result.get("type") == "skip":
            break
    return results
