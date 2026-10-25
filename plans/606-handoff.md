# Handoff: #606 Build standalone workflow-cli orchestrator

## Metadata
- Issue: #606
- Branch: feature/606-workflow-cli
- PR: none
- Status: implementing
- Created: 2026-10-25
- Fix attempts: 0

## 1. Issue
### Summary
Build a standalone, project-agnostic Python CLI (`workflow-cli`) that orchestrates a skill-based development workflow using a local LLM (via llama-swap). All workflow state lives inside the CLI's own directory tree — zero files are written into the target repo. The CLI handles all tool execution (git, gh, file I/O, linting, testing) while the local LLM acts as a structured planner — returning JSON batches of typed actions for the CLI to execute.

### Motivation
Claude Code is the current workflow orchestrator via `.claude/skills/`. This project is designed to replace it (or any proprietary AI coding assistant) with a self-contained, open tool that leaves no artifacts in the repos it operates on. It separates the orchestration engine (the CLI) from project-specific knowledge (skills, rules, hooks stored in the CLI's own `projects/` directory).

### Proposed Behavior / Steps to Reproduce
- A standalone Python package (`workflow-cli`) installable system-wide.
- `workflow-cli init <repo-path>` scans the repo for rule files, tech stack, test/lint commands, and writes a project config into `workflow-cli/projects/<repo-id>/config.yaml`.
- The CLI manages the full workflow pipeline (issue → design → plan → implement → ship) with all state stored in `workflow-cli/projects/<repo-id>/`.
- The LLM (via llama-swap) returns JSON batches of typed actions (`bash`, `gh`, `read`, `write`, `edit`, `ask_user`, `approve`, `skip`, `error`).
- The CLI executes each action, feeds results back to the LLM, and iterates until the skill completes.
- Stage gates (plan approval, ship approval) pause for user confirmation.
- State is carried by handoff files in `workflow-cli/projects/<repo-id>/handoff/` and runtime state in `workflow-cli/projects/<repo-id>/state.json`.
- The CLI is project-agnostic: it knows nothing about any specific repo. All project knowledge lives in its own `projects/` directory.
- The target repo is never modified by the CLI beyond git operations (branch create, commit, push, PR).

### Affected Area
- New standalone Python package (outside the EmuSync repo).
- Would eventually replace or supplement the current Claude Code `.claude/skills/` pipeline.
- EmuSync would be registered via `workflow-cli init ~/Github/Emusync` — no files written to the repo.

### Acceptance Criteria
- [ ] `workflow-cli init <repo-path>` scans repo, discovers rule files, tech stack, commands, writes config to `workflow-cli/projects/<repo-id>/config.yaml`
- [ ] `workflow-cli <N>` discovers project from CLI's projects directory, resumes existing workflow, or starts fresh
- [ ] `workflow-cli status` shows current workflow state (issue, branch, stage, timestamps)
- [ ] `workflow-cli cancel <N>` marks a workflow as blocked without changes
- [ ] LLM integration via llama-swap: sends prompts, parses JSON action batches, handles retries
- [ ] Action executor supports all types: bash, gh, read, write, edit, ask_user, approve, skip, error
- [ ] Stage router correctly advances through: issue → design → fplan/bplan → merge → tplan → implement → review → ship
- [ ] Handoff file read/write with the 12-section template, stored in CLI's projects directory
- [ ] Runtime state tracked in `workflow-cli/projects/<repo-id>/state.json` (LLM usage, timing, run history)
- [ ] Branch management: creates `feature/<N>-<slug>` from main, never works on main
- [ ] Progress display with stage prefixes and gate summaries
- [ ] Fix loop: detects test failures, re-invokes plan/implement, retries up to 3 times
- [ ] Server sync hook: configurable SSH command executed during ship stage
- [ ] Project-agnostic: works with a minimal config, no hardcoded repo knowledge
- [ ] Zero files written into the target repo by the CLI (except git operations)

## 2. Design
### Scope: Standalone Python CLI package (~12 modules). All state stored in CLI's own `projects/<repo-id>/` directory. Zero files written into target repo. Terminal-only output.
### Backend Changes: New package: cli.py (arg parser + main loop), config.py (project config + repo discovery), state.py (handoff + state.json in projects dir), stages.py (stage router), skills.py (skill loader + prompt builder), llm.py (llama-swap client), actions.py (action executor), progress.py (terminal output), gates.py (approval/revision logic), project.py (hook executor), prompts/ (system prompts + JSON schema). pyproject.toml, skills/, tests/.
### UI Changes: None. Terminal-only progress display with stage prefixes, gate summaries, and color-coded output.
### Plan Target: bplan
### Sub-issues: None — single cohesive tool.
### Difficulty: 7/10 — ~12 modules, LLM integration with retry logic, JSON parsing/validation, git/gh CLI orchestration, multi-stage state machine, fix loop with rollback, repo discovery on init.
### Backwards Compatibility: N/A — standalone tool outside EmuSync. Additive only.

## 3. Frontend Plan
### Design Alignment: TBD
### Visual Pattern: TBD
### Recommendations: TBD

## 4. Backend Plan
### Design Alignment: Standalone Python package, not part of EmuSync. Standard Python CLI patterns. All state stored in CLI's own directory tree (`workflow-cli/projects/<repo-id>/`). Zero files written to target repo. Uses rich for terminal output, pydantic for JSON validation, httpx for HTTP, pyyaml for config.
### Backend Pattern: Modular CLI with separate concerns: repo discovery (on init), config loading, state management (in CLI's projects dir), stage routing, skill loading (from CLI's skills/), LLM client, action execution, progress display, gate logic, hook execution. Each module is independently testable.
### Recommendations: Use click or argparse for CLI args. Use rich for colored terminal output. Use pydantic for LLM response validation. Atomic file writes for all config/state files. No external API server — CLI-only tool. `init` command does repo scanning (rule files, tech stack, test/lint commands) and writes everything into `projects/<repo-id>/`.

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: workflow-cli/tests/ (pytest, real file I/O, no mocks for state)
### Test Cases: config.py (valid/invalid parsing, defaults, repo discovery), state.py (handoff read/write, state JSON, atomic writes, Markdown parsing), stages.py (valid/invalid transitions), skills.py (discovery, overrides, prompt assembly, fallback), llm.py (HTTP POST, JSON parsing, retry, error handling), actions.py (bash/gh/read/write/edit/ask_user/approve/skip/error), progress.py (stage prefixes, gates), gates.py (approval/revision flows), project.py (hooks), cli.py (subcommands), prompts/schema.py (JSON validation)
### Edge Cases: LLM invalid JSON retry, LLM unavailable, edit not-found, corrupt handoff/config, concurrent access (file locking), empty skills dir, non-git repo
### Integration Points: init flow (cli+config+stages), skill loop (llm+skills+actions), approval flow (gates+actions), hook execution (project+actions)

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps:
- Step 1: DONE — pyproject.toml, package structure, entry point. Files: workflow-cli/pyproject.toml, workflow_cli/__init__.py, workflow_cli/__main__.py. Reuses: none. New: project structure with flat package layout.
- Step 2: DONE — YAML config parsing with PyYAML, pydantic validation. Files: workflow_cli/config.py. Reuses: none. New: config models for project settings, hooks, LLM settings; repo discovery; atomic config saves.
- Step 3: DONE (combined with step 2) — repo scanning logic in config.py (discover_repo function). Reuses: subprocess, pathlib. New: finds CLAUDE.md, CONTRIBUTING.md, docs/ARCHITECTURE.md, package.json, pyproject.toml, Makefile, etc.
- Step 4: DONE — handoff files + state.json in CLI's projects dir. Files: workflow_cli/state.py. Reuses: none. New: Markdown file I/O (create, read, update section, append log), JSON management (read, write, update run), atomic writes, 12-section template.
- Step 5: DONE — state machine for handoff status → next skill. Files: workflow_cli/stages.py. Reuses: none. New: parse_status, next_skill, validate_transition, is_terminal, needs_plan_target.
- Step 6: DONE — skill discovery with fallback (project overrides > CLI defaults), prompt assembly. Files: workflow_cli/skills.py. Reuses: config.py (_projects_dir). New: find_skill(), load_skill(), build_prompt(), load_project_rules().
- Step 7: LLM client — llama-swap HTTP client with retry. Files: workflow_cli/llm.py. Reuses: httpx. New: HTTP + JSON parsing + retry.
- Step 8: Action executor — typed action dispatch. Files: workflow_cli/actions.py. Reuses: subprocess, stdlib. New: action dispatch.
- Step 9: Progress emitter — colored terminal output. Files: workflow_cli/progress.py. Reuses: rich. New: stage prefixes + gates.
- Step 10: Gate logic — approval/revision flow. Files: workflow_cli/gates.py. Reuses: progress.py, actions.py. New: approval decisions.
- Step 11: Project hooks — server_sync, doc_sync, pre_ship. Files: workflow_cli/project.py. Reuses: config.py, actions.py. New: SSH/command execution.
- Step 12: CLI arg parser + main loop. Files: workflow_cli/cli.py. Reuses: config.py, stages.py, progress.py. New: subcommands (init, resume, status, cancel, list, plan, handoff) + main loop.
- Step 13: System prompts + JSON schema. Files: workflow_cli/prompts/system.py, prompts/schema.py. Reuses: pydantic. New: prompt templates.
- Step 14: Default skill templates. Files: workflow-cli/skills/*/SKILL.md. Reuses: EmuSync skills as reference. New: project-agnostic skills.
- Step 15: Tests. Files: workflow-cli/tests/*.py. Reuses: pytest. New: unit tests for state, stages, actions, config, progress, llm.

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
- 2026-10-25 bplan: 15 steps written, backend_pattern=standalone Python CLI with all state in CLI's projects dir, zero files in target repo
- 2026-10-25 revise: moved all state from target repo to CLI's projects/<repo-id>/ directory, added repo discovery step, removed backend design guide step
- 2026-10-25 tplan: 11 test modules defined, 4 integration points, edge cases covered (invalid JSON, corrupt files, concurrent access, non-git repo)
- 2026-10-25 implement: step 1 done (scaffolding: pyproject.toml, package structure, entry point)
- 2026-10-25 implement: step 2 done (config loader: pydantic models, repo discovery, atomic saves)
- 2026-10-25 implement: step 3 done (repo discovery — combined with step 2 into config.py)
- 2026-10-25 implement: step 4 done (state manager: handoff file CRUD, state.json, atomic writes)
- 2026-10-25 implement: step 5 done (stage router: state machine, status parsing, skill dispatch)
- 2026-10-25 implement: step 6 done (skill loader: skill discovery with fallback resolution, prompt assembly)
- 2026-10-25 implement: step 7 done (LLM client: llama-swap HTTP client with retry, JSON parsing, markdown fence stripping)
- 2026-10-25 implement: step 8 done (action executor: bash, gh, read, write, edit, ask_user, approve, skip, error dispatch)
- 2026-10-25 implement: step 9 done (progress emitter: rich-based colored output, stage prefixes, gate display)
- 2026-10-25 implement: step 10 done (gate logic: approval/revision flow, gate validation, summary formatting)
- 2026-10-25 implement: step 11 done (project hooks: server_sync, doc_sync, pre_ship execution)
- 2026-10-25 implement: step 12 done (CLI arg parser + main loop: init, resume, status, cancel, list, plan, handoff subcommands)
- 2026-10-25 implement: step 13 done (system prompts + JSON schema: action format rules, pydantic validation)
