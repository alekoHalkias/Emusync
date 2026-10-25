"""State management for workflow-cli.

Handles handoff files (12-section Markdown template) and runtime
state.json, both stored under the CLI's projects/<repo-id>/ directory.
All file writes are atomic (write-to-temp-then-rename).
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workflow_cli.config import _projects_dir


# ---------------------------------------------------------------------------
# Handoff file management
# ---------------------------------------------------------------------------

HANDOFF_TEMPLATE = """\
# Handoff: #<N> <title>

## Metadata
- Issue: #<N>
- Branch: feature/<N>-<slug>
- PR: none
- Status: created
- Created: <YYYY-MM-DD>
- Fix attempts: 0

## 1. Issue
### Summary
### Motivation
### Proposed Behavior / Steps to Reproduce
### Affected Area
### Acceptance Criteria

## 2. Design
### Scope: TBD
### Backend Changes: TBD
### UI Changes: TBD
### Plan Target: TBD (bplan / fplan / both)
### Sub-issues: TBD
### Difficulty: TBD
### Backwards Compatibility: TBD

## 3. Frontend Plan
### Design Alignment: TBD
### Visual Pattern: TBD
### Recommendations: TBD

## 4. Backend Plan
### Design Alignment: TBD
### Backend Pattern: TBD
### Recommendations: TBD

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: TBD
### Test Cases: TBD
### Edge Cases: TBD
### Integration Points: TBD

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps: TBD (written by /plan skills)

## 9. Review
### Findings: TBD
### Blocked: TBD
### Blockers: TBD

## 10. Ship
### Status: pending
### PR: none
### Server Sync: pending
### Doc Sync: pending

## 11. Fix Attempts
### Attempt 1: none
### Attempt 2: none
### Attempt 3: none

## 12. Log
- <YYYY-MM-DD> workflow initialized
"""


def _handoff_dir(project_id: str) -> Path:
    """Return the handoff directory for a project."""
    return _projects_dir() / project_id / "handoff"


def _handoff_path(project_id: str, issue_number: int) -> Path:
    """Return the handoff file path for an issue."""
    return _handoff_dir(project_id) / f"{issue_number}-handoff.md"


def create_handoff(project_id: str, issue_number: int, title: str) -> Path:
    """Create a new handoff file with the 12-section template."""
    path = _handoff_path(project_id, issue_number)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = HANDOFF_TEMPLATE.replace("<N>", str(issue_number)).replace(
        "<title>", title
    ).replace("<YYYY-MM-DD>", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    _atomic_write(path, content)
    return path


def read_handoff(project_id: str, issue_number: int) -> str | None:
    """Read a handoff file. Returns None if it doesn't exist."""
    path = _handoff_path(project_id, issue_number)
    if not path.is_file():
        return None
    return path.read_text()


def update_handoff_section(
    project_id: str,
    issue_number: int,
    section_header: str,
    content: str,
) -> None:
    """Replace content under a handoff section header (### Header).

    If the header doesn't exist, appends the content before the next
    section or at the end of the file.
    """
    path = _handoff_path(project_id, issue_number)
    if not path.is_file():
        raise FileNotFoundError(f"Handoff file not found: {path}")

    text = path.read_text()
    header_pattern = rf"(^{re.escape(section_header)}\n)(.*?)(?=\n## |\Z)"

    new_section = f"{section_header}\n{content}\n"
    updated = re.sub(header_pattern, new_section, text, flags=re.DOTALL | re.MULTILINE)

    if updated == text:
        # Header not found — append before the last section (## 12. Log)
        log_idx = text.find("## 12. Log")
        if log_idx >= 0:
            updated = text[:log_idx] + f"\n{new_section}" + text[log_idx:]
        else:
            updated = text.rstrip() + f"\n\n{new_section}"

    _atomic_write(path, updated)


def append_handoff_log(project_id: str, issue_number: int, entry: str) -> None:
    """Append a timestamped entry to the ## 12. Log section."""
    path = _handoff_path(project_id, issue_number)
    if not path.is_file():
        raise FileNotFoundError(f"Handoff file not found: {path}")

    text = path.read_text()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_line = f"- {timestamp} {entry}"

    log_idx = text.find("## 12. Log")
    if log_idx >= 0:
        # Find the end of the Log section
        log_section_end = text.find("\n## ", log_idx + 1)
        if log_section_end < 0:
            # End of file
            updated = text.rstrip() + "\n" + log_line + "\n"
        else:
            updated = text[:log_section_end] + log_line + "\n" + text[log_section_end:]
    else:
        updated = text.rstrip() + f"\n\n## 12. Log\n- {log_line}\n"

    _atomic_write(path, updated)


# ---------------------------------------------------------------------------
# Runtime state management
# ---------------------------------------------------------------------------

def _state_path(project_id: str) -> Path:
    """Return the state.json path for a project."""
    return _projects_dir() / project_id / "state.json"


def read_state(project_id: str) -> dict[str, Any]:
    """Read the runtime state file. Returns empty dict if not found."""
    path = _state_path(project_id)
    if not path.is_file():
        return {"runs": {}}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"runs": {}}


def write_state(project_id: str, state: dict[str, Any]) -> None:
    """Write the runtime state file atomically."""
    path = _state_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, json.dumps(state, indent=2) + "\n")


def update_run_state(
    project_id: str,
    issue_number: int,
    updates: dict[str, Any],
) -> None:
    """Update fields for a specific run in state.json."""
    state = read_state(project_id)
    runs = state.setdefault("runs", {})
    run = runs.setdefault(str(issue_number), {})
    run.update(updates)
    run["updated_at"] = datetime.now(timezone.utc).isoformat()
    write_state(project_id, state)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _atomic_write(path: Path, content: str) -> None:
    """Write content to a file atomically (write-to-temp then rename)."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content)
    os.chmod(path.parent / tmp.name, 0o644)
    tmp.rename(path)
