"""Project hooks: execute server_sync, doc_sync, pre_ship hooks from config.

Hooks are defined in the project config and executed as bash actions
when the workflow reaches the ship stage.
"""

from __future__ import annotations

import logging
import subprocess
from typing import Any

from workflow_cli.config import ProjectSettings

logger = logging.getLogger(__name__)

HookResult = dict[str, Any]


def _execute_hook_command(command: str, cwd: str | None = None, timeout: float = 300) -> HookResult:
    """Execute a single hook command."""
    logger.info("Executing hook: %s", command[:100])
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
            "command": command,
            "ok": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        return {
            "command": command,
            "ok": False,
            "exit_code": -1,
            "stderr": f"Hook timed out after {timeout}s",
        }
    except Exception as e:
        return {
            "command": command,
            "ok": False,
            "exit_code": -1,
            "stderr": str(e),
        }


def execute_server_sync(config: ProjectSettings, repo_root: str) -> HookResult:
    """Execute the server_sync hook.

    Typically SSHes to the server PC and pulls the latest code + restarts.
    """
    command = config.hooks.server_sync
    if not command:
        return {"hook": "server_sync", "ok": True, "skipped": True, "reason": "No server_sync configured"}

    # Replace placeholders
    command = command.replace("{repo_root}", repo_root)

    result = _execute_hook_command(command, cwd=repo_root)
    result["hook"] = "server_sync"
    return result


def execute_doc_sync(config: ProjectSettings, repo_root: str) -> HookResult:
    """Execute the doc_sync hook.

    Copies documentation to a docs site or triggers a doc build.
    """
    command = config.hooks.doc_sync
    if not command:
        return {"hook": "doc_sync", "ok": True, "skipped": True, "reason": "No doc_sync configured"}

    command = command.replace("{repo_root}", repo_root)

    result = _execute_hook_command(command, cwd=repo_root)
    result["hook"] = "doc_sync"
    return result


def execute_pre_ship(config: ProjectSettings, repo_root: str) -> HookResult:
    """Execute the pre_ship hook.

    Runs validation checks before shipping (e.g., lint, build).
    """
    command = config.hooks.pre_ship
    if not command:
        return {"hook": "pre_ship", "ok": True, "skipped": True, "reason": "No pre_ship configured"}

    command = command.replace("{repo_root}", repo_root)

    result = _execute_hook_command(command, cwd=repo_root)
    result["hook"] = "pre_ship"
    return result


def execute_all_hooks(config: ProjectSettings, repo_root: str) -> dict[str, HookResult]:
    """Execute all configured hooks in order.

    Returns a dict of hook_name → result.
    Stops on first failure (except skipped hooks).
    """
    results = {}

    # Server sync first
    results["server_sync"] = execute_server_sync(config, repo_root)
    if not results["server_sync"].get("ok", True):
        return results  # Don't continue if server sync fails

    # Doc sync second
    results["doc_sync"] = execute_doc_sync(config, repo_root)
    # Doc sync failure is non-fatal (logged but doesn't stop)

    # Pre-ship last (must pass)
    results["pre_ship"] = execute_pre_ship(config, repo_root)

    return results
