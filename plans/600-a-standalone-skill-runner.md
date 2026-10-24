# Plan: #600 — Standalone skill runner with isolated context per step

Status: implementing
**Branch:** feature/600-standalone-skill-runner
**Created:** 2026-01-04
**Last updated:** 2026-01-04

## Scope

Build a standalone, project-agnostic skill runner that orchestrates the EmuSync workflow pipeline (issue → design → plan → implement → review → ship) by:
- Reading a handoff file to determine current stage
- Building a minimal context snapshot per skill
- Calling an LLM (local OpenAI-compatible API by default, Claude Code CLI as fallback)
- Parsing structured LLM output and writing back to handoff/plan files
- Looping until workflow completes

**No changes to EmuSync product code.** Pure infrastructure.

## Architecture

```
run-skill.sh ──→ skill-runner.sh (main entry point)
                    │
                    ├─ lib/config.sh    — config loading (env > project file > defaults)
                    ├─ lib/context.sh   — builds prompt from handoff + skill + issue
                    ├─ lib/response.sh  — parses LLM response, extracts sections
                    ├─ lib/model.sh     — API caller (local/openai/claude-code)
                    ├─ lib/workflow.sh  — status→skill mapping, loop logic
                    ├─ lib/git.sh       — git operations (branch, commit, push)
                    ├─ lib/github.sh    — gh CLI operations (issue, PR, merge)
                    └─ prompts/         — per-skill prompt templates
```

## Design decisions

1. **Runner is a dumb pipe** — no project-specific logic. LLM does all reasoning.
2. **Local LLM first** — OpenAI-compatible API (llama.cpp, llama-swap/Strata) is default.
3. **Claude Code fallback** — `claude code -p` when configured.
4. **Single entry point** — one script, no dependencies, POSIX-ish bash.
5. **Generic handoff format** — works with any project's handoff/plan files.
6. **Context compression** — only include relevant sections, not full GOTCHAS.md.

## Implementation steps

### Step 1: Skeleton and config
- Create `scripts/skill-runner/` directory structure
- Write `lib/config.sh` — config loading with env/project/defaults priority
- Write `skill-runner.sh` — argument parsing, main loop skeleton
- Write `lib/workflow.sh` — status→skill mapping, next-skill logic

### Step 2: Context building and model calling
- Write `lib/context.sh` — reads handoff, fetches issue, builds prompt
- Write `lib/model.sh` — API caller supporting local/openai/claude-code backends
- Write prompt templates in `prompts/` directory

### Step 3: Response parsing and file writing
- Write `lib/response.sh` — parses LLM response, writes handoff/plan updates
- Wire up full pipeline: read → build prompt → call LLM → parse → write → loop

### Step 4: Git and GitHub operations
- Write `lib/git.sh` — branch create/checkout, commit, push
- Write `lib/github.sh` — issue create, PR create, merge, status check
- Integrate into main loop

### Step 5: Testing and documentation
- Test with a real issue (this one: #600)
- Write README for the skill-runner
- Verify all skills work end-to-end

## Acceptance criteria

- [ ] Runner script exists at `scripts/skill-runner/skill-runner.sh`
- [ ] Runner reads `plans/<N>-handoff.md` to determine next skill
- [ ] Context snapshot is generated per-skill (only relevant sections)
- [ ] Each skill runs in a fresh LLM call (no inherited context)
- [ ] Skill output writes back to handoff file and plan files
- [ ] Runner loops until workflow reaches `shipped` or `blocked` status
- [ ] All existing skills remain compatible (same handoff/plan format)
- [ ] Documented usage: `scripts/skill-runner/skill-runner.sh <issue-number>`
- [ ] Supports local OpenAI-compatible API (default) and Claude Code CLI (fallback)
