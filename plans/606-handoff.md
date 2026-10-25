# Handoff: #606 Build standalone workflow-cli orchestrator

## Metadata
- Issue: #606
- Branch: feature/606-workflow-cli
- PR: none
- Status: planned
- Created: 2026-10-25
- Fix attempts: 0

## 1. Issue
### Summary
Build a standalone, project-agnostic Python CLI (`workflow-cli`) that orchestrates a skill-based development workflow using a local LLM (via llama-swap). The CLI handles all tool execution (git, gh, file I/O, linting, testing) while the local LLM acts as a structured planner — returning JSON batches of typed actions for the CLI to execute.

### Motivation
Claude Code is the current workflow orchestrator via `.claude/skills/`. This project is designed to replace it (or any proprietary AI coding assistant) with a self-contained, open tool that any project can adopt by providing its own skill definitions, rules, and configuration. It separates the orchestration engine (the CLI) from project-specific knowledge (skills, rules, hooks in config files).

### Proposed Behavior / Steps to Reproduce
- A standalone Python package (`workflow-cli`) installable system-wide.
- Projects configure their own skills, rules, and hooks via `.workflow-cli/config.yaml`.
- The CLI discovers the project root, reads config, and manages the full workflow pipeline (issue → design → plan → implement → ship).
- The LLM (via llama-swap) returns JSON batches of typed actions (`bash`, `gh`, `read`, `write`, `edit`, `ask_user`, `approve`, `skip`, `error`).
- The CLI executes each action, feeds results back to the LLM, and iterates until the skill completes.
- Stage gates (plan approval, ship approval) pause for user confirmation.
- State is carried by a handoff file (`plans/<N>-handoff.md`) and a secondary runtime state file (`.workflow-cli/state.json`).
- The CLI is project-agnostic: it knows nothing about any specific repo. All project knowledge lives in config files.

### Affected Area
- New standalone Python package (outside the EmuSync repo, or optionally vendored within it).
- Would eventually replace or supplement the current Claude Code `.claude/skills/` pipeline.
- EmuSync would adopt it by writing a `.workflow-cli/config.yaml` and copying/linking skill definitions.

### Acceptance Criteria
- [ ] `workflow-cli init` scaffolds `.workflow-cli/config.yaml` in a project root
- [ ] `workflow-cli <N>` discovers project, resumes existing workflow, or starts fresh
- [ ] `workflow-cli status` shows current workflow state (issue, branch, stage, timestamps)
- [ ] `workflow-cli cancel <N>` marks a workflow as blocked without changes
- [ ] LLM integration via llama-swap: sends prompts, parses JSON action batches, handles retries
- [ ] Action executor supports all types: bash, gh, read, write, edit, ask_user, approve, skip, error
- [ ] Stage router correctly advances through: issue → design → fplan/bplan → merge → tplan → implement → review → ship
- [ ] Handoff file read/write with the 12-section template
- [ ] Runtime state tracked in `.workflow-cli/state.json` (LLM usage, timing, run history)
- [ ] Branch management: creates `feature/<N>-<slug>` from main, never works on main
- [ ] Progress display with stage prefixes and gate summaries
- [ ] Fix loop: detects test failures, re-invokes plan/implement, retries up to 3 times
- [ ] Server sync hook: configurable SSH command executed during ship stage
- [ ] Project-agnostic: works with a minimal config, no hardcoded repo knowledge

## 2. Design
### Scope: Standalone Python CLI package (~12 modules). No EmuSync code touched. Terminal-only output.
### Backend Changes: New package: cli.py (arg parser + main loop), config.py (project config loading), state.py (handoff + state.json), stages.py (stage router), skills.py (skill loader + prompt builder), llm.py (llama-swap client), actions.py (action executor), progress.py (terminal output), gates.py (approval/revision logic), project.py (config loader + hook executor), prompts/ (system prompts + JSON schema). pyproject.toml, tests/.
### UI Changes: None. Terminal-only progress display with stage prefixes, gate summaries, and color-coded output.
### Plan Target: bplan
### Sub-issues: None — single cohesive tool.
### Difficulty: 7/10 — ~12 modules, LLM integration with retry logic, JSON parsing/validation, git/gh CLI orchestration, multi-stage state machine, fix loop with rollback.
### Backwards Compatibility: N/A — standalone tool outside EmuSync. Additive only.

## 3. Frontend Plan
### Design Alignment: TBD
### Visual Pattern: TBD
### Recommendations: TBD

## 4. Backend Plan
### Design Alignment: Standalone Python package, not part of EmuSync. Standard Python CLI patterns. Uses rich for terminal output, pydantic for JSON validation, httpx for HTTP, pyyaml for config.
### Backend Pattern: Modular CLI with separate concerns: config loading, state management, stage routing, skill loading, LLM client, action execution, progress display, gate logic, hook execution. Each module is independently testable.
### Recommendations: Use click or argparse for CLI args. Use rich for colored terminal output. Use pydantic for LLM response validation. Atomic file writes for all config/state files. No external API server — CLI-only tool.

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
### Steps:
- Step 1: Scaffolding — pyproject.toml, package structure, entry point. Files: workflow-cli/pyproject.toml, workflow_cli/__init__.py, workflow_cli/__main__.py. Reuses: none. New: project structure.
- Step 2: Config loader — YAML config parsing with PyYAML, pydantic validation. Files: workflow_cli/config.py. Reuses: none. New: config models.
- Step 3: State manager — handoff file + state.json management. Files: workflow_cli/state.py. Reuses: none. New: Markdown/JSON file I/O.
- Step 4: Stage router — state machine for handoff status → next skill. Files: workflow_cli/stages.py. Reuses: none. New: stage transition logic.
- Step 5: Skill loader — read SKILL.md, inject context. Files: workflow_cli/skills.py. Reuses: none. New: prompt assembly.
- Step 6: LLM client — llama-swap HTTP client with retry. Files: workflow_cli/llm.py. Reuses: httpx. New: HTTP + JSON parsing + retry.
- Step 7: Action executor — typed action dispatch. Files: workflow_cli/actions.py. Reuses: subprocess, stdlib. New: action dispatch.
- Step 8: Progress emitter — colored terminal output. Files: workflow_cli/progress.py. Reuses: rich. New: stage prefixes + gates.
- Step 9: Gate logic — approval/revision flow. Files: workflow_cli/gates.py. Reuses: progress.py, actions.py. New: approval decisions.
- Step 10: Project hooks — server_sync, doc_sync, pre_ship. Files: workflow_cli/project.py. Reuses: config.py, actions.py. New: SSH/command execution.
- Step 11: CLI arg parser + main loop. Files: workflow_cli/cli.py. Reuses: config.py, stages.py, progress.py. New: subcommands + main loop.
- Step 12: System prompts + JSON schema. Files: workflow_cli/prompts/system.py, prompts/schema.py. Reuses: pydantic. New: prompt templates.
- Step 13: Default skill templates. Files: workflow-cli/skills/*/SKILL.md. Reuses: EmuSync skills as reference. New: project-agnostic skills.
- Step 14: Tests. Files: workflow-cli/tests/*.py. Reuses: pytest. New: unit tests.
- Step 15: Backend design guide. Files: .claude/backend-design-guide.md. Reuses: none. New: workflow-cli patterns doc.

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
- 2026-10-25 issue: workflow initialized, issue #606 created
- 2026-10-25 design: scope=standalone Python CLI (~12 modules), plan_target=bplan, difficulty=7/10, breaking=no
- 2026-10-25 bplan: 15 steps written, backend_pattern=standalone Python CLI with llama-swap integration
