#!/usr/bin/env python3
"""PreToolUse hook: block edits to tracked repo files unless /implement is working an approved plan.

Allowed: paths outside the repo, src/plans/, .claude/. Everything else needs a
feature/<N>-* branch whose src/plans/<N>-*.md has `Status: implementing`.
Exit 2 blocks the tool call and shows stderr to Claude.
"""
import glob
import json
import os
import re
import subprocess
import sys

# ponytail: only gates Edit/Write/NotebookEdit; shell edits (sed, >) bypass it.


def git(cwd, *args):
    # Drop GIT_DIR etc. (set inside git hooks) so cwd decides the repo.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True).stdout.strip()


def check(data):
    """Return None if allowed, else the reason to block."""
    tool_input = data.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("notebook_path")
    cwd = data.get("cwd") or os.getcwd()
    root = git(cwd, "rev-parse", "--show-toplevel")
    if not path or not root:
        return None
    rel = os.path.relpath(os.path.realpath(os.path.join(cwd, path)), os.path.realpath(root))
    if rel.startswith("..") or rel.startswith(".claude") or rel.startswith("src/plans"):
        return None

    branch = git(root, "branch", "--show-current")
    m = re.match(r"[a-z][a-z0-9_-]*/(\d+)-", branch)
    if not m:
        return f"Branch '{branch}' is not linked to an issue. Code changes go through /issue -> /plan -> /implement."
    n = m.group(1)
    plans = glob.glob(os.path.join(root, "src", "plans", f"{n}-*.md"))
    if not plans:
        return f"No plan file src/plans/{n}-*.md. Run /plan {n} first."
    with open(plans[0]) as f:
        status = re.search(r"^\s*-?\s*Status:\s*(\S+)", f.read(), re.M)
    if not status or status.group(1) != "implementing":
        found = status.group(1) if status else "missing"
        return f"Plan for #{n} has Status: {found}. Code edits only happen under /implement {n} (Status: implementing)."
    return None


if __name__ == "__main__":
    reason = check(json.load(sys.stdin))
    if reason:
        print(reason, file=sys.stderr)
        sys.exit(2)
