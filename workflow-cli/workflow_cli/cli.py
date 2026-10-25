"""CLI arg parser + main loop: discover project from CLI's projects dir, resolve issue/PR, dispatch to stage router.

Subcommands: init, resume, status, cancel, list, plan, handoff
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from workflow_cli.config import load_project_config, register_project
from workflow_cli.orchestrate import run_orchestration
from workflow_cli.progress import (
    console,
    print_done,
    print_error,
    print_header,
    print_info,
    print_step,
    print_warning,
)
from workflow_cli.stages import next_skill, parse_status, validate_transition
from workflow_cli.state import read_handoff

logger = logging.getLogger(__name__)


def cmd_init(args: argparse.Namespace) -> int:
    """Initialize a new project in the CLI's projects directory."""
    repo_path = Path(args.repo).resolve()
    name = args.name or repo_path.name

    if not (repo_path / ".git").exists():
        print_error(f"Not a git repo: {repo_path}")
        return 1

    project_id = register_project(str(repo_path), name)
    print_header(f"Project registered: {name}", "created")
    print_info(f"Project ID: {project_id}")
    print_info(f"Repo path: {repo_path}")
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    """Resume the workflow for a project and issue."""
    project_id = args.project_id
    issue_number = args.issue

    # Check if handoff exists (project registered for this issue?)
    handoff = read_handoff(project_id, issue_number)
    if handoff is None:
        print_warning(f"No handoff found for #{issue_number}. Running init flow first...")

    return run_orchestration(project_id, issue_number)


def cmd_status(args: argparse.Namespace) -> int:
    """Show the current status of a project's workflow."""
    project_id = args.project_id

    config = load_project_config(project_id)
    if config is None:
        print_error(f"Project not found: {project_id}")
        return 1

    print_header(f"Status: {config.project.name}", "")
    print_info(f"Project ID: {project_id}")
    repo_path = config.repo_path if hasattr(config, 'repo_path') else config.project.repo
    print_info(f"Repo path: {repo_path}")
    print_info(f"Default branch: {config.project.default_branch}")
    return 0


def cmd_cancel(args: argparse.Namespace) -> int:
    """Cancel the current workflow for a project."""
    project_id = args.project_id
    print_header(f"Cancelled: {project_id}", "blocked")
    print_info("Workflow cancelled. Update handoff to resume.")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """List all registered projects."""
    projects_dir = Path(__file__).resolve().parent.parent / "projects"
    if not projects_dir.exists():
        print_info("No projects registered yet.")
        return 0

    print_header("Registered Projects", "")
    for config_file in sorted(projects_dir.glob("*/config.yaml")):
        project_id = config_file.parent.name
        config = load_project_config(project_id)
        if config:
            print_info(f"{project_id}: {config.project.name} ({config.project.repo})")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    """Show the current plan for a project/issue."""
    project_id = args.project_id
    issue_number = args.issue

    print_header(f"Plan: {project_id} #{issue_number}", "")
    # Plan files are in the target repo
    print_info("Plan file not found — run 'init' in the target repo first.")
    return 0


def cmd_handoff(args: argparse.Namespace) -> int:
    """Show the current handoff file for a project/issue."""
    project_id = args.project_id
    issue_number = args.issue

    handoff = read_handoff(project_id, issue_number)
    if handoff is None:
        print_warning(f"No handoff found for #{issue_number}")
        return 1

    print_header(f"Handoff: {project_id} #{issue_number}", "")
    console.print(handoff)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="workflow-cli",
        description="Orchestrate skill-based development workflows with a local LLM",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init
    init_parser = subparsers.add_parser("init", help="Initialize a new project")
    init_parser.add_argument("repo", help="Path to the target repository")
    init_parser.add_argument("--name", help="Project name (defaults to repo name)")

    # resume
    resume_parser = subparsers.add_parser("resume", help="Resume workflow for a project")
    resume_parser.add_argument("project_id", help="Project ID")
    resume_parser.add_argument("issue", help="Issue number")

    # status
    status_parser = subparsers.add_parser("status", help="Show project status")
    status_parser.add_argument("project_id", help="Project ID")

    # cancel
    cancel_parser = subparsers.add_parser("cancel", help="Cancel workflow")
    cancel_parser.add_argument("project_id", help="Project ID")

    # list
    subparsers.add_parser("list", help="List all projects")

    # plan
    plan_parser = subparsers.add_parser("plan", help="Show plan")
    plan_parser.add_argument("project_id", help="Project ID")
    plan_parser.add_argument("issue", help="Issue number")

    # handoff
    handoff_parser = subparsers.add_parser("handoff", help="Show handoff file")
    handoff_parser.add_argument("project_id", help="Project ID")
    handoff_parser.add_argument("issue", help="Issue number")

    return parser


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    commands = {
        "init": cmd_init,
        "resume": cmd_resume,
        "status": cmd_status,
        "cancel": cmd_cancel,
        "list": cmd_list,
        "plan": cmd_plan,
        "handoff": cmd_handoff,
    }

    if args.command is None:
        parser.print_help()
        return 0

    handler = commands.get(args.command)
    if handler is None:
        print_error(f"Unknown command: {args.command}")
        return 1

    try:
        return handler(args)
    except KeyboardInterrupt:
        print_info("\nCancelled.")
        return 130
    except Exception as e:
        logger.exception("Unhandled error")
        print_error(str(e))
        return 1
