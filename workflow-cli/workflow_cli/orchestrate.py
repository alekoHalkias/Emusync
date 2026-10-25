"""Orchestration loop: LLM → skill → actions → handoff update → loop.

Ties together the LLM client, skill loader, action executor, state manager,
progress emitter, gate logic, and project hooks into a single loop.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from workflow_cli.actions import execute_actions
from workflow_cli.config import ProjectSettings, load_project_config
from workflow_cli.gates import (
    format_approval_summary,
    format_revision_feedback,
    gate_decision,
    needs_approval,
    validate_transition,
)
from workflow_cli.llm import LLMClient
from workflow_cli.progress import (
    console,
    print_action_result,
    print_approval_request,
    print_done,
    print_error,
    print_final_summary,
    print_header,
    print_info,
    print_llm_response,
    print_prompt_summary,
    print_step,
    print_warning,
)
from workflow_cli.project import execute_all_hooks
from workflow_cli.skills import build_prompt, find_skill, load_project_rules, load_skill
from workflow_cli.state import (
    append_handoff_log,
    create_handoff,
    read_handoff,
    read_state,
    update_handoff_section,
    write_state,
)
from workflow_cli.stages import (
    is_terminal,
    next_skill,
    parse_status,
    validate_transition,
)

logger = logging.getLogger(__name__)


def _load_code_context(repo_root: Path, paths: list[str]) -> list[dict[str, str]]:
    """Load code files requested by the LLM for context."""
    context = []
    for p in paths:
        full = (repo_root / p).resolve()
        if full.is_file():
            try:
                content = full.read_text()
                context.append({"path": str(full), "content": content})
            except Exception as e:
                logger.warning("Could not read code context %s: %s", p, e)
    return context


def _run_turn(
    llm: LLMClient,
    prompt: str,
    skill_name: str,
    turn: int,
    project_id: str,
    issue_number: str,
    repo_root: Path,
) -> dict[str, Any]:
    """Execute a single LLM turn: prompt → response → actions → update.

    Returns the parsed response dict.
    """
    print_step(turn, 0, f"Running {skill_name} skill (turn {turn})")

    # Send to LLM
    messages = [{"role": "user", "content": prompt}]
    response = llm.chat(system_prompt="", messages=messages)

    print_llm_response(str(response))

    # Check for parse failure
    if response.get("_parse_failed"):
        print_error("LLM returned unparseable response")
        return response

    # Extract actions
    actions = response.get("actions", [])
    if actions:
        results = execute_actions(actions)
        for result in results:
            print_action_result(result)

    # Update state
    response["turn"] = turn
    response["skill"] = skill_name
    return response


def run_orchestration(project_id: str, issue_number: str) -> int:
    """Run the full workflow orchestration loop.

    This is the main entry point for the resume command. It reads the
    handoff file, determines the current status, dispatches the appropriate
    skill, executes actions, and loops until the workflow reaches a terminal
    state (shipped or blocked).

    Returns 0 on success, 1 on error.
    """
    # Load project config
    config = load_project_config(project_id)
    if config is None:
        print_error(f"Project not found: {project_id}")
        return 1

    projects_dir = Path(__file__).resolve().parent.parent / "projects"
    project_dir = projects_dir / project_id
    if not project_dir.exists():
        print_error(f"Project directory not found: {project_dir}")
        return 1

    # Use the stored repo_path from config
    repo_path_str = config.repo_path if hasattr(config, 'repo_path') and config.repo_path else ""
    if not repo_path_str:
        print_warning("No repo_path in config — using project directory")
        repo_root = project_dir.parent.parent
    else:
        repo_root = Path(repo_path_str)
        if not repo_root.is_dir():
            print_warning(f"Stored repo_path not found: {repo_path_str}")
            repo_root = project_dir.parent.parent

    # Initialize LLM client from config
    llama_url = config.llama_swap.url if hasattr(config, 'llama_swap') else "http://localhost:8001"
    llm = LLMClient(base_url=llama_url)

    # Read or create handoff
    handoff = read_handoff(project_id, issue_number)
    if handoff is None:
        print_header(f"Creating handoff for issue #{issue_number}", "created")
        create_handoff(project_id, issue_number, f"Issue #{issue_number}")
        handoff = read_handoff(project_id, issue_number)

    # Determine initial status
    status = parse_status(handoff) or "created"
    print_header(f"Orchestrating: {project_id} #{issue_number}", status)
    print_info(f"Current status: {status}")

    # Load project rules
    rule_files = config.rule_files if hasattr(config, 'rule_files') else ["CLAUDE.md"]
    rules = load_project_rules(project_id, rule_files)

    # Load plan context if available
    plan_path = repo_root / "plans" / f"{issue_number}-workflow-cli.md"
    plan_context = ""
    if plan_path.is_file():
        plan_context = plan_path.read_text()

    # Main loop
    turn = 1
    max_turns = 50  # Safety limit
    approvals: dict[str, bool] = {}

    while not is_terminal(status) and turn <= max_turns:
        # Determine current skill from status
        skill_name = next_skill(handoff)
        if skill_name is None:
            print_error(f"Cannot determine skill for status: {status}")
            break

        print_header(f"Skill: {skill_name}", status)

        # Check if gate requires approval
        if needs_approval(status):
            summary = format_approval_summary(status, f"Status: {status}\nHandoff for issue #{issue_number}")
            decision = gate_decision(status, summary)

            if decision == "revise":
                # Format revision feedback
                feedback = format_revision_feedback(status, "User requested revision")
                handoff = feedback + "\n\n" + handoff
                status = "implementing"
                update_handoff_section(project_id, issue_number, "Status", f"- Status: {status}")
                append_handoff_log(project_id, issue_number, f"Revised on {status}")
                continue
            elif decision == "approve":
                approvals[status] = True
                update_handoff_section(project_id, issue_number, "Status", f"- Status: approved")
                status = "shipped" if status == "implemented" else "implementing"
                update_handoff_section(project_id, issue_number, "Status", f"- Status: {status}")
                continue
            elif decision is None:
                # User input needed — would be handled by ask_user action in real impl
                print_warning("User input required — skipping gate for now")

        # Build prompt
        code_context = []  # Would be populated by LLM requests in real impl

        prompt = build_prompt(
            skill_name=skill_name,
            system_prompt="",  # Would come from prompts/system.py
            project_rules=rules,
            handoff_context=handoff,
            plan_context=plan_context,
            code_context=code_context,
            project_id=project_id,
        )

        # Print prompt summary
        print_prompt_summary(
            system_len=0,  # Would be len(system_prompt)
            skill_len=len(load_skill(skill_name, project_id) or ""),
            handoff_len=len(handoff),
            code_len=sum(len(c["content"]) for c in code_context),
        )

        # Execute LLM turn
        response = _run_turn(
            llm=llm,
            prompt=prompt,
            skill_name=skill_name,
            turn=turn,
            project_id=project_id,
            issue_number=issue_number,
            repo_root=repo_root,
        )

        # Check for stage completion
        if response.get("stage_complete"):
            next_skill_name = response.get("next_skill")
            output = response.get("output", "")

            # Update handoff section
            if next_skill_name:
                new_status_map = {
                    "issue": "created",
                    "fplan": "design",
                    "bplan": "planning",
                    "merge": "planning",
                    "tplan": "planning",
                    "implement": "implementing",
                    "review": "implemented",
                    "ship": "shipped",
                }
                new_status = new_status_map.get(next_skill_name, status)
                update_handoff_section(project_id, issue_number, "Status", f"- Status: {new_status}")
                status = new_status

            # Append output to handoff if present
            if output:
                update_handoff_section(
                    project_id,
                    issue_number,
                    f"## {turn}. Output",
                    output,
                )

            append_handoff_log(project_id, issue_number, f"Skill {skill_name} complete, next: {next_skill_name}")
            print_final_summary(status, next_skill_name, output)
        else:
            # Continue with next turn
            turn += 1
            continue

        turn += 1

    # Terminal state reached
    if is_terminal(status):
        print_header(f"Workflow complete: {status}", status)
        if status == "shipped":
            # Execute project hooks
            hooks_result = execute_all_hooks(config, str(repo_root))
            for hook_name, result in hooks_result.items():
                if result.get("ok") or result.get("skipped"):
                    print_info(f"Hook {hook_name}: OK")
                else:
                    print_error(f"Hook {hook_name} failed: {result.get('stderr', 'unknown')}")
    elif turn > max_turns:
        print_error(f"Reached max turns ({max_turns}) — workflow stuck")

    return 0
