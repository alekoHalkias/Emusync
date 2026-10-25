# Plan: #606 Build standalone workflow-cli orchestrator

Issue: #606
Branch: feature/606-workflow-cli
PR: none
Status: planned
Fix attempts: 0

## Goal
Build a standalone, project-agnostic Python CLI that orchestrates a skill-based development workflow using a local LLM (via llama-swap), with JSON-batch action execution, stage gates, and project configuration via YAML.

## Design Alignment
- **Backend Pattern**: New standalone Python package, not part of EmuSync. Follows standard Python CLI patterns (click-like arg parsing, modular architecture). No EmuSync code touched.
- **Recommendations**: Use `rich` for terminal progress display (color-coded stage prefixes, gate summaries). Use `pydantic` for JSON schema validation of LLM responses. Use `httpx` for llama-swap HTTP client. Use `pyyaml` for project config. No external API server — CLI-only tool.

## Steps
- [ ] 1. Scaffolding: pyproject.toml, package structure, entry point
  - Files: workflow-cli/pyproject.toml, workflow-cli/workflow_cli/__init__.py, workflow-cli/workflow_cli/__main__.py
  - Reuses: none — new project
  - New: project structure with standard Python layout (src-style or flat pkg)

- [ ] 2. Config loader: read .workflow-cli/config.yaml, validate required fields, provide defaults
  - Files: workflow-cli/workflow_cli/config.py
  - Reuses: none
  - New: YAML config parsing with PyYAML, field validation (pydantic models for ProjectConfig, LlamaSwapConfig, HooksConfig)

- [ ] 3. State manager: read/write handoff file (12-section template) and runtime state.json
  - Files: workflow-cli/workflow_cli/state.py
  - Reuses: none — but follows same handoff template as EmuSync skills
  - New: Markdown file parsing/writing for handoff, JSON management for state.json, atomic writes

- [ ] 4. Stage router: read handoff status, determine next skill, handle stage transitions
  - Files: workflow-cli/workflow_cli/stages.py
  - Reuses: none
  - New: state machine mapping handoff status → next skill, with validation of valid transitions

- [ ] 5. Skill loader: read SKILL.md from configured skills_dir, inject context (project rules, handoff, plan file, code files)
  - Files: workflow-cli/workflow_cli/skills.py
  - Reuses: none
  - New: skill discovery from project config, prompt assembly (system + skill + rules + handoff + plan + code), context file injection

- [ ] 6. LLM client: send prompts to llama-swap, parse JSON action batches, handle retries and timeouts
  - Files: workflow-cli/workflow_cli/llm.py
  - Reuses: httpx (from deps)
  - New: HTTP POST to llama-swap endpoint, JSON response parsing with pydantic validation, exponential backoff retry (3 attempts), model error handling

- [ ] 7. Action executor: execute typed actions (bash, gh, read, write, edit, ask_user, approve, skip, error)
  - Files: workflow-cli/workflow_cli/actions.py
  - Reuses: subprocess for bash/gh, stdlib for file I/O
  - New: action dispatch by type, result collection, ask_user integration with user input, edit with exact string matching

- [ ] 8. Progress emitter: color-coded stage prefixes, gate summaries, step progress
  - Files: workflow-cli/workflow_cli/progress.py
  - Reuses: rich (from deps)
  - New: stage prefix mapping ([ISSUE], [DESIGN], [BPLAN], etc.), progress bars for steps, gate display with approval prompts

- [ ] 9. Gate logic: plan approval, ship approval, revision feedback loop
  - Files: workflow-cli/workflow_cli/gates.py
  - Reuses: progress.py for display, actions.py for ask_user
  - New: summary rendering, approve/revise/reject decision flow, revision feedback formatting for LLM

- [ ] 10. Project hooks: execute server_sync, doc_sync, pre_ship hooks from config
  - Files: workflow-cli/workflow_cli/project.py (hooks section)
  - Reuses: config.py for hook config, actions.py for bash execution
  - New: SSH command execution for server_sync, file sync for doc_sync, pre-ship validation commands

- [ ] 11. CLI arg parser + main loop: discover project, resolve issue/PR, dispatch to stage router
  - Files: workflow-cli/workflow_cli/cli.py
  - Reuses: config.py for project discovery, stages.py for routing, progress.py for output
  - New: subcommands (init, resume, status, cancel, list, plan, handoff), project root discovery (.workflow-cli/config.yaml), main orchestration loop

- [ ] 12. System prompts and JSON schema: generic action format instructions, LLM response schema
  - Files: workflow-cli/workflow_cli/prompts/system.py, workflow-cli/workflow_cli/prompts/schema.py
  - Reuses: pydantic for schema validation
  - New: system prompt templates (action format rules, no-emoji policy, handoff-as-state-carrier), JSON action schema (action types, output format)

- [ ] 13. Default skill templates: copy default SKILL.md files for all pipeline stages
  - Files: workflow-cli/skills/issue/SKILL.md, fplan/SKILL.md, bplan/SKILL.md, merge/SKILL.md, tplan/SKILL.md, test-design/SKILL.md, implement/SKILL.md, review/SKILL.md, ship/SKILL.md
  - Reuses: EmuSync's .claude/skills/ as reference (not copied, but adapted)
  - New: project-agnostic skill definitions that reference project config for rules and hooks

- [ ] 14. Tests: unit tests for state, stages, actions, llm, config, progress
  - Files: workflow-cli/tests/test_state.py, test_stages.py, test_actions.py, test_llm.py, test_config.py, test_progress.py
  - Reuses: pytest (from dev deps)
  - New: real file I/O tests (no mocks for state), HTTP mock for llama-swap, subprocess mock for actions

- [ ] 15. Backend design guide: create .claude/backend-design-guide.md entry for workflow-cli patterns
  - Files: .claude/backend-design-guide.md
  - Reuses: none
  - New: document workflow-cli patterns (config structure, state management, action format, skill loading) for future EmuSync-based workflow-cli development

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: yes (workflow-cli). Config/data file change: no (new project).

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
- 2026-10-25 bplan: 15 steps written, backend_pattern=standalone Python CLI with llama-swap integration
