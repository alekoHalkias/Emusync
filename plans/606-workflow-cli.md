# Plan: #606 Build standalone workflow-cli orchestrator

Issue: #606
Branch: feature/606-workflow-cli
PR: none
Status: implementing
Fix attempts: 0

## Goal
Build a standalone, project-agnostic Python CLI that orchestrates a skill-based development workflow using a local LLM (via llama-swap), with JSON-batch action execution, stage gates, and project configuration stored entirely within the CLI's own directory tree — zero files written into the target repo.

## Design Alignment
- **Backend Pattern**: New standalone Python package, not part of EmuSync. All state stored in CLI's own `projects/<repo-id>/` directory. Zero files written to target repo. Follows standard Python CLI patterns (click-like arg parsing, modular architecture).
- **Recommendations**: Use `rich` for terminal progress display. Use `pydantic` for JSON schema validation. Use `httpx` for llama-swap HTTP client. Use `pyyaml` for project config. No external API server — CLI-only tool. `init` command scans repo and writes config into `projects/<repo-id>/`.

## Steps
- [x] 1. Scaffolding: pyproject.toml, package structure, entry point
  - Files: workflow-cli/pyproject.toml, workflow-cli/workflow_cli/__init__.py, workflow-cli/workflow_cli/__main__.py
  - Reuses: none — new project
  - New: project structure with flat package layout

- [x] 2. Config loader: YAML config parsing with PyYAML, pydantic validation
  - Files: workflow-cli/workflow_cli/config.py
  - Reuses: none
  - New: pydantic models for ProjectConfig, LlamaSwapConfig, HooksConfig; repo discovery (rule files, tech stack, test/lint commands, git info); atomic config saves

- [x] 3. Repo discovery: scan target repo for rule files, tech stack, test/lint commands, git info
  - Files: workflow-cli/workflow_cli/config.py (discover_repo function)
  - Reuses: subprocess, pathlib
  - New: repo scanning logic — finds CLAUDE.md, CONTRIBUTING.md, docs/ARCHITECTURE.md, package.json, pyproject.toml, Makefile, etc.

- [x] 4. State manager: handoff files + state.json in CLI's projects dir
  - Files: workflow-cli/workflow_cli/state.py
  - Reuses: none — follows same 12-section handoff template as EmuSync skills
  - New: Markdown file parsing/writing, JSON management, paths under `projects/<repo-id>/handoff/` and `projects/<repo-id>/state.json`, atomic writes

- [x] 5. Stage router: read handoff status, determine next skill, handle stage transitions
  - Files: workflow-cli/workflow_cli/stages.py
  - Reuses: none
  - New: state machine mapping handoff status → next skill, with validation of valid transitions

- [x] 6. Skill loader: read SKILL.md from CLI's skills/ dir or projects/<repo-id>/skills/ (overrides), inject context
  - Files: workflow-cli/workflow_cli/skills.py
  - Reuses: none
  - New: skill discovery with fallback resolution, prompt assembly (system + skill + rules + handoff + plan + code), context file injection

- [x] 7. LLM client: send prompts to llama-swap, parse JSON action batches, handle retries and timeouts
  - Files: workflow-cli/workflow_cli/llm.py
  - Reuses: httpx (from deps)
  - New: HTTP POST to llama-swap endpoint, JSON response parsing with pydantic validation, exponential backoff retry (3 attempts), model error handling

- [x] 8. Action executor: execute typed actions (bash, gh, read, write, edit, ask_user, approve, skip, error)
  - Files: workflow-cli/workflow_cli/actions.py
  - Reuses: subprocess for bash/gh, stdlib for file I/O
  - New: action dispatch by type, result collection, ask_user integration, edit with exact string matching

- [x] 9. Progress emitter: color-coded stage prefixes, gate summaries, step progress
  - Files: workflow-cli/workflow_cli/progress.py
  - Reuses: rich (from deps)
  - New: stage prefix mapping ([ISSUE], [DESIGN], [BPLAN], etc.), progress bars for steps, gate display with approval prompts

- [x] 10. Gate logic: plan approval, ship approval, revision feedback loop
  - Files: workflow-cli/workflow_cli/gates.py
  - Reuses: progress.py for display, actions.py for ask_user
  - New: summary rendering, approve/revise/reject decision flow, revision feedback formatting for LLM

- [x] 11. Project hooks: execute server_sync, doc_sync, pre_ship hooks from config
  - Files: workflow-cli/workflow_cli/project.py
  - Reuses: config.py for hook config, actions.py for bash execution
  - New: SSH command execution for server_sync, file sync for doc_sync, pre-ship validation commands

- [x] 12. CLI arg parser + main loop: discover project from CLI's projects dir, resolve issue/PR, dispatch to stage router
  - Files: workflow-cli/workflow_cli/cli.py
  - Reuses: config.py for project lookup, stages.py for routing, progress.py for output
  - New: subcommands (init, resume, status, cancel, list, plan, handoff), project lookup by repo path or name, main orchestration loop

- [ ] 13. System prompts and JSON schema: generic action format instructions, LLM response schema
  - Files: workflow-cli/workflow_cli/prompts/system.py, workflow-cli/workflow_cli/prompts/schema.py
  - Reuses: pydantic for schema validation
  - New: system prompt templates (action format rules, no-emoji policy, handoff-as-state-carrier), JSON action schema

- [ ] 14. Default skill templates: SKILL.md files for all pipeline stages
  - Files: workflow-cli/skills/issue/SKILL.md, fplan/SKILL.md, bplan/SKILL.md, merge/SKILL.md, tplan/SKILL.md, test-design/SKILL.md, implement/SKILL.md, review/SKILL.md, ship/SKILL.md
  - Reuses: EmuSync's .claude/skills/ as reference (adapted, not copied)
  - New: project-agnostic skill definitions that reference project config for rules and hooks

- [ ] 15. Tests: unit tests for state, stages, actions, llm, config, progress
  - Files: workflow-cli/tests/test_state.py, test_stages.py, test_actions.py, test_llm.py, test_config.py, test_progress.py
  - Reuses: pytest (from dev deps)
  - New: real file I/O tests (no mocks for state), HTTP mock for llama-swap, subprocess mock for actions

## Testing
- **Test File**: workflow-cli/tests/ (pytest, real file I/O, no mocks for state)
- **Test Cases**:
  - config.py: valid config parsing, invalid config handling, default values, repo discovery (rule files found/missing, tech stack detection, graceful missing files)
  - state.py: handoff file read/write (12-section template), state JSON read/write, atomic writes, path resolution, Markdown section parsing
  - stages.py: valid transitions (created→designed→planned→implementing→implemented→shipped), invalid transitions rejected, status parsing from handoff
  - skills.py: skill discovery from CLI's skills/, override resolution from projects/<repo-id>/skills/, prompt assembly, fallback when skill not found
  - llm.py: HTTP POST to llama-swap, JSON response parsing, retry logic (3 attempts, exponential backoff), model error handling, timeout handling
  - actions.py: bash action (command execution, stdout/stderr/exit_code), gh action, read action, write action (atomic), edit action (exact string match, not-found error), ask_user, approve, skip/error
  - progress.py: stage prefix output, gate display, color coding
  - gates.py: plan approval flow, ship approval flow, revision feedback loop
  - project.py: server_sync hook execution, doc_sync hook execution, pre-ship validation
  - cli.py: subcommand parsing (init, resume, status, cancel, list, plan, handoff), project discovery
  - prompts/schema.py: JSON schema validation of LLM responses
- **Edge Cases**:
  - LLM returns invalid JSON (retry with reformatted prompt)
  - LLM endpoint unavailable (health check, error report)
  - Edit action with old_string not found (report with context, no auto-retry)
  - Handoff file corrupt/malformed (error, do not crash)
  - Config file corrupt (error, do not proceed)
  - Concurrent workflow access (file locking for state.json)
  - Empty skills directory (error with helpful message)
  - Target repo without .git (init fails with error)
- **Integration Points**:
  - cli.py + config.py + stages.py: full init flow (discover project, create config, create branch)
  - llm.py + skills.py + actions.py: full skill execution loop (prompt → LLM → actions → results → next prompt)
  - gates.py + actions.py: user approval flow (present summary → capture decision → proceed or revise)
  - project.py + actions.py: hook execution (server sync via SSH, doc sync via file copy)

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: yes (workflow-cli). Config/data file change: no (new project, state stored in CLI's own directory).

## Not in this plan
- Smart model routing (deferred to follow-up)
- Webhook integration
- LLM cost tracking and budget limits
- Multiple repo support (one CLI invocation per repo)
- Dry-run mode
- Verbose mode
- Skill versioning / update management
- `workflow-cli share` for scaffolding new projects

## Log
- 2026-10-25 bplan: 15 steps written, backend_pattern=standalone Python CLI with all state in CLI's projects dir, zero files in target repo
