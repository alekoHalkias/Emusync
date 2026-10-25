"""Progress emitter: color-coded stage prefixes, gate summaries, step progress.

Uses rich for terminal output with stage-specific colors and formatting.
"""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()

# Stage prefix mapping: status → (prefix_color, prefix_label)
STAGE_PREFIXES = {
    "created": ("blue", "[ISSUE]"),
    "design": ("cyan", "[DESIGN]"),
    "fplan": ("cyan", "[FPPLAN]"),
    "bplan": ("cyan", "[BPLAN]"),
    "merge": ("cyan", "[MERGE]"),
    "tplan": ("yellow", "[TPPLAN]"),
    "implementing": ("green", "[IMPL]"),
    "implemented": ("green", "[REVIEW]"),
    "review": ("magenta", "[REVIEW]"),
    "shipped": ("green", "[SHIP]"),
    "blocked": ("red", "[BLOCKED]"),
}

DEFAULT_PREFIX = ("white", "[WORKFLOW]")


def stage_prefix(status: str) -> tuple[str, str]:
    """Get the (color, prefix) for a given status."""
    return STAGE_PREFIXES.get(status, DEFAULT_PREFIX)


def print_header(title: str, status: str = "") -> None:
    """Print a section header with stage-appropriate color."""
    color, prefix = stage_prefix(status)
    console.print()
    console.print(Text(f"{prefix} {title}", style=f"bold {color}"))
    console.print()


def print_step(step_num: int, total_steps: int, description: str) -> None:
    """Print a step progress line."""
    progress = Text()
    progress.append(f"Step {step_num}/{total_steps}: ", style="bold cyan")
    progress.append(description, style="white")
    console.print(progress)


def print_done(step_num: int, description: str) -> None:
    """Print a completed step marker."""
    console.print(Text(f"  [done] Step {step_num}: {description}", style="green"))


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(Text(f"ERROR: {message}", style="bold red"))


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(Text(f"WARNING: {message}", style="bold yellow"))


def print_info(message: str) -> None:
    """Print an info message."""
    console.print(Text(f"INFO: {message}", style="blue"))


def print_gate(title: str, summary: str, options: list[str]) -> None:
    """Print a gate summary panel."""
    panel = Panel(
        Text(summary, style="white"),
        title=Text(title, style="bold cyan"),
        border_style="cyan",
    )
    console.print(panel)
    console.print(f"Options: {', '.join(options)}")


def print_action_result(result: dict[str, Any]) -> None:
    """Print the result of an action execution."""
    action_type = result.get("type", "unknown")
    ok = result.get("ok", False)

    if ok:
        console.print(Text(f"  [ok] {action_type}", style="green"))
    else:
        error = result.get("error", result.get("stderr", "Unknown error"))
        console.print(Text(f"  [fail] {action_type}: {error}", style="red"))

    # Show stdout for bash/gh actions (truncated)
    if action_type in ("bash", "gh"):
        stdout = result.get("stdout", "")
        if stdout:
            lines = stdout.split("\n")
            display_lines = lines[:3]
            console.print(Text(f"    stdout: {'; '.join(display_lines)}", style="dim"))
            if len(lines) > 3:
                console.print(Text(f"    ... ({len(lines)} total lines)", style="dim"))


def print_llm_response(content: str) -> None:
    """Print a summary of an LLM response."""
    console.print(Text(f"  LLM: {len(content)} chars received", style="dim"))


def print_prompt_summary(system_len: int, skill_len: int, handoff_len: int, code_len: int) -> None:
    """Print a summary of what's being sent to the LLM."""
    parts = []
    if system_len:
        parts.append(f"system={system_len}B")
    if skill_len:
        parts.append(f"skill={skill_len}B")
    if handoff_len:
        parts.append(f"handoff={handoff_len}B")
    if code_len:
        parts.append(f"code={code_len}B")
    console.print(Text(f"  prompt: {', '.join(parts)}", style="dim"))


def print_approval_request(question: str, options: list[str]) -> None:
    """Print an approval request."""
    console.print()
    console.print(Text(f"Approval needed:", style="bold yellow"))
    console.print(f"  {question}")
    console.print(f"  Options: {', '.join(options)}")
    console.print()


def print_final_summary(status: str, next_skill: str | None, output: str) -> None:
    """Print the final summary of a skill execution."""
    color, prefix = stage_prefix(status)
    console.print()
    panel = Panel(
        Text(output, style="white") if output else Text("(no output)", style="dim"),
        title=Text(f"{prefix} Complete", style=f"bold {color}"),
        border_style=color,
    )
    console.print(panel)
    if next_skill:
        console.print(Text(f"Next skill: {next_skill}", style="bold cyan"))
