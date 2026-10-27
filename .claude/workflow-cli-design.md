# Workflow CLI — Agentic System Design

A deterministic Python orchestrator that chains Claude Code skills (issue → design → fplan/bplan → merge → tplan → implement → review → ship) through a handoff-file state machine. Claude is the reasoning engine; the CLI is the disciplined executor.

## Problem

The Claude skills (`.claude/skills/*`) are well-designed modular prompts but require manual human invocation at each stage. The old skill-runner had the infrastructure (state machine, handoff parser, git ops) but was incomplete. The old workflow-cli had a more complete architecture but its source is lost. We need a single system that:

1. Reads the handoff file to determine current stage
2. Invokes Claude with the appropriate skill prompt
3. Parses Claude's output and updates the handoff
4. Commits, pushes, and advances to the next stage
5. Loops until ship completes (or failure)

## Architecture Overview

```
tools/workflow-cli/
├── workflow_cli/
│   ├── __main__.py          # Entry point: `python -m workflow_cli`
│   ├── cli.py               # Click CLI: run, stage, status, resume
│   ├── config.py            # Config loading (.tools/workflow-cli/config.json)
│   ├── project.py           # Repo detection, paths, handoff resolution
│   ├── state.py             # Handoff file read/write (YAML frontmatter + sections)
│   ├── stages.py            # Stage definitions, transitions, entry/exit hooks
│   ├── skills.py            # Skill invocation (Claude subprocess/API)
│   ├── llm.py               # Claude API client (structured output)
│   ├── gates.py             # Precondition checks per stage
│   ├── actions.py           # Git, GitHub CLI, SSH operations
│   ├── progress.py          # Logging, status display, handoff log
│   └── prompts/
│       ├── __init__.py      # Prompt registry: get_prompt(skill_name, handoff)
│       ├── schema.py        # Output schema definitions per skill
│       └── system.py        # System prompt template (shared context)
├── docs/
│   └── DESIGN.md            # This file
├── pyproject.toml
└── README.md
```

## Module Specifications

### `cli.py` — Click CLI

```
workflow-cli run <issue_id|description>   # Auto-run full pipeline
workflow-cli stage <number>               # Run single stage
workflow-cli status                       # Show current handoff state
workflow-cli resume                       # Resume interrupted run
workflow-cli reset <number>               # Reset handoff to a stage
```

- `run` is the main entry point. Resolves issue, creates handoff if needed, enters the orchestration loop.
- `stage` is for debugging — runs one skill and exits.
- `status` prints a summary of the handoff file (status, section lengths, plan steps).
- `resume` and `reset` are convenience wrappers around stage + state manipulation.

### `config.py` — Configuration

```python
# .tools/workflow-cli/config.json
{
    "repo_path": "/home/Aleko/Documents/Scripts/Emusync",
    "claude_api_key": "...",              # or use ANTHROPIC_API_KEY env var
    "claude_model": "claude-sonnet-5-5",
    "github_token_path": "/home/Aleko/.github_token",
    "server_ssh": "server@192.168.4.111",
    "llama_swap_url": null,               # fallback for analysis tasks
    "max_fix_attempts": 3,
    "auto_push": true,
    "auto_sync_server": true
}
```

- Loads from `.tools/workflow-cli/config.json` in the repo root.
- Falls back to environment variables (`ANTHROPIC_API_KEY`, `GH_TOKEN`).
- `repo_path` is auto-detected from git if not specified.

### `project.py` — Repo & Path Management

```python
def detect_repo(root: Path) -> Path
def resolve_handoff(repo: Path, issue_id: int | str) -> Path
def resolve_branch(repo: Path, issue_id: int | str) -> str
def ensure_branch(repo: Path, issue_id: int | str) -> None
```

- `detect_repo`: walks up from cwd to find `.git/`.
- `resolve_handoff`: returns `plans/<N>-handoff.md` where N is the numeric issue ID.
- `resolve_branch`: returns `feature/<N>-<slug>` where slug comes from the issue title.
- `ensure_branch`: creates the feature branch from main if it doesn't exist.

### `state.py` — Handoff File Management

The handoff file is the single source of truth for workflow state. Every module reads/writes through this.

```python
# Handoff structure:
# ---
# issue: 123
# branch: feature/123-fix-sync
# pr: none
# status: designed
# fix_attempts: 0
# ---
#
# ## 1. Issue
# <summary, motivation, acceptance criteria>
#
# ## 2. Design
# <scope analysis, plan target, difficulty>
#
# ... (sections 3-11) ...
#
# ## 12. Log
# - 2025-01-15 14:30 issue: created
# - 2025-01-15 14:35 design: scope=backend, difficulty=4/10
```

```python
Handoff = TypedDict("Handoff", {
    "frontmatter": dict[str, str | int | bool | None],
    "sections": dict[str, str],
})

def read_handoff(path: Path) -> Handoff
def write_handoff(path: Path, data: Handoff) -> None
def update_status(path: Path, status: str, **overrides) -> None
def get_status(path: Path) -> str | None
def append_section(path: Path, title: str, content: str) -> None
def append_log(path: Path, entry: str) -> None
def check_plan_steps(path: Path) -> tuple[int, int]  # (checked, total)
```

- Uses the same format as the skill-runner's handoff parser (YAML frontmatter + `## N. Title` sections).
- `append_section` appends to an existing section or creates a new one.
- `append_log` appends a timestamped entry to section 12.
- `check_plan_steps` counts `- [x]` vs `- [ ]` in the Implementation Steps section.

### `stages.py` — Stage Definitions

Each stage has: a name, a status value, a list of prerequisite skills, entry/exit hooks, and the next-stage mapping.

```python
Stage = namedtuple("Stage", [
    "name",           # e.g. "issue", "design", "implement"
    "status",         # e.g. "created", "designed", "implementing"
    "requires",       # list of statuses that must be complete before this
    "entry_hook",     # callable: run when entering the stage (e.g. create branch)
    "exit_hook",      # callable: run when leaving (e.g. commit handoff)
    "next_on_success",# status to set on success
    "next_on_failure",# status to set on failure
])

STAGES = [
    Stage("issue",     "created",    [],         create_branch,  commit_handoff, "designed",     "blocked"),
    Stage("design",    "designed",   ["created"], None,           commit_handoff, "planning",     "blocked"),
    Stage("bplan",     "planning",   ["designed"], None,          commit_handoff, "planned",      "blocked"),
    Stage("fplan",     "planned",    ["designed"], None,          commit_handoff, "planned",      "blocked"),
    Stage("merge",     "planned",    ["planning", "planned"], merge_plans, commit_handoff, "planned", "blocked"),
    Stage("tplan",     "planned",    ["planned"],  None,          commit_handoff, "planned",      "blocked"),
    Stage("implement", "implementing", ["planned"], validate_plan, commit_handoff, "implemented", "blocked"),
    Stage("review",    "reviewed",   ["implemented"], run_review,  commit_handoff, "reviewed",    "blocked"),
    Stage("ship",      "shipped",    ["reviewed"],  run_tests,    commit_handoff, "shipped",      "blocked"),
]

def resolve_next(handoff: Handoff, repo: Path) -> Stage
def transition(handoff: Path, stage: Stage, success: bool) -> None
```

Key design: stages are declarative. The `resolve_next` function reads the handoff status and returns the next stage to run. Entry/exit hooks handle side effects (branch creation, git commits, etc.).

### `skills.py` — Skill Invocation

This is the bridge between the deterministic engine and Claude. Each skill has a prompt, an output schema, and a handler.

```python
# Skills are divided into two categories:
# 1. DETERMINISTIC: no LLM needed (issue, docs, merge)
# 2. CLAUDE-INVOKING: need Claude's reasoning (design, fplan, bplan, tplan, implement, review, ship)

SkillHandler = Callable[[Handoff, Config, Path], SkillResult]

class SkillResult:
    success: bool
    handoff_updates: dict[str, str]  # section_title -> new content
    metadata_updates: dict[str, Any]  # frontmatter key -> value
    error: str | None
    requires_user_input: bool  # pause for human decision?

def invoke_skill(skill_name: str, handoff: Handoff, config: Config, repo: Path) -> SkillResult
```

**Claude invocation flow:**
1. Load the skill's prompt from `prompts/__init__.py`
2. Load the system prompt from `prompts/system.py` (includes CLAUDE.md rules, GOTCHAS.md key rules, project context)
3. Load the handoff file content (all sections)
4. Call Claude API with structured output (JSON matching the skill's schema)
5. Parse the response, validate against schema
6. Apply handoff updates, return result

**Deterministic skills** (issue, docs, merge):
- `issue`: Creates GitHub issue, resolves branch name, creates handoff file
- `docs`: Runs diff against main, identifies stale docs, updates them
- `merge`: Reconciles fplan + bplan plan files into one (text-based diff/merge)

### `llm.py` — Claude API Client

```python
class ClaudeClient:
    def __init__(self, api_key: str, model: str)

    def chat(self, system: str, messages: list[dict], schema: type[BaseModel]) -> T
    def chat_raw(self, system: str, messages: list[dict]) -> str
```

- Uses the Anthropic Messages API with structured output (JSON schema).
- `chat` returns a typed result matching the skill's output schema.
- `chat_raw` returns raw text for skills that produce markdown.
- Includes retry logic (exponential backoff, max 3 retries).
- Timeout: 120s per call.

**Why API over CLI?** The CLI is blocking, verbose, and hard to parse. The API gives structured JSON output, which is essential for the handoff file updates. The Claude skills' SKILL.md files become the system prompt; the user's issue description becomes the first user message.

### `gates.py` — Precondition Checks

```python
# Each gate returns (ok: bool, reason: str)
# If any gate fails, the stage is skipped and the error is reported.

GATES = {
    "issue":     [has_github_token, repo_is_clean],
    "design":    [handoff_exists, issue_exists],
    "fplan":     [handoff_exists, design_complete, has_frontend_changes],
    "bplan":     [handoff_exists, design_complete, has_backend_changes],
    "merge":     [handoff_exists, fplan_done, bplan_done],
    "tplan":     [handoff_exists, plan_done],
    "implement": [handoff_exists, plan_complete, branch_exists],
    "review":    [handoff_exists, implementation_complete],
    "ship":      [handoff_exists, review_complete, tests_passing],
}

def check_gates(stage: str, handoff: Handoff, repo: Path) -> list[tuple[str, bool, str]]
```

Gates run before each skill invocation. If a gate fails, the engine reports the issue and either:
- Auto-fixes (e.g., creates a missing branch)
- Pauses for user input
- Sets status to "blocked" and exits

### `actions.py` — Git, GitHub, SSH Operations

```python
class GitOps:
    def create_branch(repo: Path, branch: str, from_branch: str = "main") -> None
    def commit(repo: Path, message: str, paths: list[str]) -> str  # returns commit hash
    def push(repo: Path, branch: str, set_upstream: bool = False) -> None
    def diff_against(repo: Path, against: str) -> str  # returns git diff
    def get_changed_files(repo: Path, against: str) -> list[str]

class GhOps:
    def create_issue(repo: Path, title: str, body: str) -> int
    def view_issue(repo: Path, number: int) -> dict
    def update_issue(repo: Path, number: int, body: str) -> None
    def create_pr(repo: Path, title: str, body: str, branch: str, base: str = "main") -> int
    def view_pr(repo: Path, number: int) -> dict
    def check_mergeable(repo: Path, number: int) -> bool

class SshOps:
    def sync_server(ssh_user: str, ssh_host: str, repo_path: str, branch: str) -> tuple[bool, str]
```

- All operations are wrapped in try/except with clear error messages.
- Git operations include branch checks before checkout.
- SSH ops are only used during ship (server sync).

### `progress.py` — Logging & Status Display

```python
def log(handoff_path: Path, stage: str, message: str) -> None
def print_status(handoff_path: Path) -> None
def print_progress(stage: str, message: str, done: bool = False) -> None
```

- `log`: Appends timestamped entry to handoff section 12.
- `print_status`: Pretty-prints the handoff file summary (status, sections, plan steps).
- `print_progress`: Prints a line to stdout with stage name and message. On completion, adds a checkmark.

### `prompts/` — Claude Skill Prompts

This is the critical bridge. Each Claude skill's `SKILL.md` becomes a prompt template here.

```python
# prompts/__init__.py
SKILL_PROMPTS = {
    "issue":     "issue.prompt",
    "design":    "design.prompt",
    "fplan":     "fplan.prompt",
    "bplan":     "bplan.prompt",
    "merge":     "merge.prompt",
    "tplan":     "tplan.prompt",
    "implement": "implement.prompt",
    "review":    "review.prompt",
    "ship":      "ship.prompt",
    "docs":      "docs.prompt",
}

def get_prompt(skill: str, handoff: Handoff) -> PromptBundle:
    """Returns (system_prompt, user_message, output_schema)"""
```

**Prompt structure per skill:**

```
System prompt (from prompts/system.py):
  - Project context (EmuSync stack, CLAUDE.md key rules)
  - Workflow state (current stage, what's been done)
  - Output format requirements (JSON schema)

User message (from prompts/<skill>.prompt):
  - The skill's step-by-step instructions (adapted from SKILL.md)
  - The handoff content (sections 1 through current)
  - The specific task for this skill

Output schema (from prompts/schema.py):
  - JSON schema defining the expected output structure
  - Used for structured output validation
```

**Example: `design.prompt`**
```
You are performing the design stage of the EmuSync workflow.

CONTEXT:
- Issue #<N>: <title>
- Issue body: <body>
- Current handoff sections: <sections 1-2>

TASK:
1. Read the full issue.
2. Analyze scope: identify backend vs UI changes.
3. Check backwards compatibility (schema, API, config, IPC).
4. Decompose to minimize scope.
5. Assess difficulty (1-10).

OUTPUT:
Provide your analysis as JSON matching the design schema.
Include: backend_summary, ui_summary, plan_target, sub_issues, difficulty, breaking_changes, compatibility_details.
```

### `orchestrate.py` — Main Loop

```python
def run(issue_id: str | int, config: Config, repo: Path) -> int:
    """
    Main orchestration loop. Returns exit code (0 = success, 1 = failure).

    Flow:
    1. Resolve issue number and handoff path
    2. If no handoff exists, create one (issue stage)
    3. Loop:
       a. Read handoff, resolve current stage
       b. Check gates
       c. Invoke skill (deterministic or Claude)
       d. Apply handoff updates
       e. Commit and push
       f. Log progress
       g. If stage complete, advance status
       h. If all stages complete, exit 0
    4. On failure: handle fix loops, set blocked status
    """
```

**The loop:**
```python
while True:
    handoff = read_handoff(handoff_path)
    stage = resolve_next(handoff, repo)

    if stage.name == "done":
        return 0  # All complete

    # Check gates
    failures = check_gates(stage.name, handoff, repo)
    if failures:
        for gate, ok, reason in failures:
            if not ok:
                log(handoff_path, stage.name, f"Gate '{gate}' failed: {reason}")
        if all_not_fixable(failures):
            update_status(handoff_path, "blocked")
            return 1
        # Try to auto-fix, or pause for user input

    # Invoke skill
    result = invoke_skill(stage.name, handoff, config, repo)

    # Apply updates
    if result.handoff_updates:
        for title, content in result.handoff_updates.items():
            append_section(handoff_path, title, content)
    if result.metadata_updates:
        update_status(handoff_path, **result.metadata_updates)

    # Commit
    git_ops.commit(handoff_path, f"#{issue_id}: {stage.name} complete")
    if config.auto_push:
        git_ops.push(repo, branch)

    # Log
    append_log(handoff_path, f"{stage.name}: {'success' if result.success else 'failed'}")

    # Handle result
    if not result.success:
        handle_failure(stage, result, handoff_path, issue_id)
        return 1  # Or enter fix loop

    # Advance status
    transition(handoff_path, stage, success=True)
```

**Fix loop (in ship stage):**
```python
if stage.name == "ship" and not tests_pass:
    fix_attempts = handoff["fix_attempts"]
    if fix_attempts >= config.max_fix_attempts:
        write_failure_report(handoff_path, result)
        update_status(handoff_path, "blocked")
        return 1

    # Re-invoke: plan fix → implement fix → ship again
    handoff["fix_attempts"] = fix_attempts + 1
    # The implement skill handles fix-plan mode
    result = invoke_skill("implement", handoff, config, repo, mode="fix")
    # Then re-run ship
```

## Error Handling

| Error | Handling |
|-------|----------|
| Claude API rate limit | Retry with exponential backoff (3 attempts), then pause for user |
| Claude API error (malformed output) | Retry once with stricter schema validation, then report to user |
| Git conflict | Stop, report to user, do not auto-merge |
| GitHub API error | Retry once, then report to user |
| SSH connection failure | Log failure, continue (don't block ship) |
| Test failure in ship | Enter fix loop (max 3 attempts) |
| Plan step blocker | Stop, write rollback state, report to user |
| Handoff file corruption | Create new handoff from issue, log warning |

## Configuration File

```json
{
    "repo_path": "/home/Aleko/Documents/Scripts/Emusync",
    "claude_model": "claude-sonnet-5-5",
    "github_token_path": "/home/Aleko/.github_token",
    "server_ssh": "server@192.168.4.111",
    "max_fix_attempts": 3,
    "auto_push": true,
    "auto_sync_server": true,
    "auto_sync_docs": true,
    "timeout_seconds": 120,
    "retry_max": 3
}
```

## Migration from Claude Skills

The Claude skills in `.claude/skills/*` remain as the source of truth for skill instructions. The workflow-cli's `prompts/` module is a **derived artifact** — it extracts the step-by-step instructions from each SKILL.md and reformats them for the API call format.

This means:
1. The SKILL.md files are the canonical source (human-readable, Claude Code invocable)
2. The workflow-cli prompts are machine-readable versions of the same instructions
3. When a SKILL.md changes, the corresponding prompt file should be updated
4. The system prompt (shared context) is common to all skills and includes CLAUDE.md rules

## Key Design Decisions

1. **Claude API over CLI**: Structured JSON output is essential for handoff updates. The CLI is too noisy and blocking.
2. **Handoff file as single state carrier**: Every module reads/writes through it. No in-memory state between runs.
3. **One commit per stage**: Atomic, resumable. An interrupted run can resume from the last committed stage.
4. **Gates before skills**: Fail fast on missing prerequisites rather than letting Claude waste tokens on an impossible task.
5. **Deterministic skills separate from Claude skills**: Issue creation, docs sync, and merge are deterministic — no LLM needed. This saves cost and is faster.
6. **Fix loop in ship, not generic**: Only ship has a fix loop (test failures → plan fix → implement → ship again). Other stages fail hard and report to user.
7. **Server sync is post-ship, not blocking**: SSH sync happens after PR creation. If it fails, the PR still exists and the handoff logs the failure.

## Future Extensions

- **Parallel skill execution**: fplan and bplan could run in parallel (both depend on design, neither depends on the other).
- **LLM fallback**: If Claude API is unavailable, fall back to llama-swap for analysis tasks (design, planning).
- **Webhook integration**: GitHub PR events could trigger re-runs (e.g., CI failure → auto-fix).
- **Multi-repo support**: One workflow CLI instance managing multiple repos.
- **Skill plugins**: Allow custom skills beyond the built-in set (e.g., `deploy`, `release`).
