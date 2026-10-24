# Skill Runner

A standalone, project-agnostic workflow orchestrator that runs skills sequentially through an LLM, with each skill reading only a compressed context snapshot from the previous step.

## Architecture

```
skill-runner.sh ──→ lib/
    │               ├─ config.sh     — config loading (env > project > defaults)
    │               ├─ workflow.sh   — status→skill mapping, loop logic
    │               ├─ context.sh    — builds prompt from handoff + skill + issue
    │               ├─ model.sh      — API caller (local/openai/claude-code)
    │               ├─ response.sh   — parses LLM response, writes files
    │               ├─ git.sh        — git operations
    │               └─ github.sh     — gh CLI operations
    │
    └─── prompts/
        ├─ issue.prompt
        ├─ design.prompt
        ├─ plan.prompt
        ├─ implement.prompt
        ├─ review.prompt
        └─ ship.prompt
```

## Usage

```bash
# Fresh issue — pass a description; skill-runner creates the GitHub issue + handoff
scripts/skill-runner/skill-runner.sh "add dark mode to the device list"

# Resume an existing issue by number
scripts/skill-runner/skill-runner.sh 600

# With options
scripts/skill-runner/skill-runner.sh 600 --model local --step fix

# Dry run (build prompt, show size, exit)
scripts/skill-runner/skill-runner.sh 600 --dry-run

# Skip git operations
scripts/skill-runner/skill-runner.sh 600 --no-commit --no-push
```

When given a description (not a number), the runner:
1. Creates `plans/<slug>-handoff.md` with `Status: created`
2. Runs the `issue` skill which creates the GitHub issue and populates the handoff
3. Continues through the pipeline automatically

## Options

| Flag | Description | Default |
|------|-------------|---------|
| `--model <backend>` | `local`, `openai`, or `claude-code` | `local` |
| `--step <slug>` | Branch slug | `step` |
| `--no-commit` | Skip git commit after each skill | false |
| `--no-push` | Skip git push | false |
| `--dry-run` | Build prompt and exit | false |
| `--max-iterations <N>` | Max loop iterations | 50 |

## Configuration

### Environment Variables

```bash
export EMUSYNC_DEFAULT_MODEL=local          # local | openai | claude-code
export EMUSYNC_API_URL=http://localhost:8080/v1
export EMUSYNC_API_KEY=sk-your-key          # optional
export EMUSYNC_MAX_TOKENS=4096
export EMUSYNC_TEMPERATURE=0.3
export EMUSYNC_MODEL_NAME=local             # model name for API
```

### Per-Project Config

Create `.claude/skill-runner.conf` in your project root:

```ini
EMUSYNC_DEFAULT_MODEL=local
EMUSYNC_API_URL=http://localhost:8080/v1
EMUSYNC_API_KEY=
EMUSYNC_MAX_TOKENS=4096
EMUSYNC_TEMPERATURE=0.3
EMUSYNC_MODEL_NAME=local
```

### Model Backends

**Local (default)** — Any OpenAI-compatible API (llama.cpp, llama-swap, Strata, Ollama, etc.)

```bash
EMUSYNC_API_URL=http://localhost:8080/v1
EMUSYNC_MODEL_NAME=llama3.1:70b
```

**OpenAI** — OpenAI's API

```bash
EMUSYNC_MODEL=openai
EMUSYNC_API_URL=https://api.openai.com/v1
EMUSYNC_API_KEY=sk-...
EMUSYNC_MODEL_NAME=gpt-4o
```

**Claude Code** — Claude Code CLI (requires `claude` binary)

```bash
EMUSYNC_MODEL=claude-code
```

## Handoff File Format

The handoff file lives at `plans/<N>-handoff.md` and has these sections:

| Section | Skill | Content |
|---------|-------|---------|
| 1. Issue | issue | Summary, motivation, acceptance criteria |
| 2. Design | design | Scope, affected areas, difficulty |
| 3. Frontend Plan | design | UI changes, visual patterns |
| 4. Backend Plan | design | API/DB changes, patterns |
| 5. Merged Plan | design | Conflict resolution |
| 6. Testing Plan | plan | Test cases, edge cases |
| 7. Test Design | plan | Test types, affected tests |
| 8. Implementation Steps | implement | Numbered steps with file paths |
| 9. Review | review | Findings, blockers |
| 10. Ship | ship | PR status, server/doc sync |
| 11. Fix Attempts | all | Record of failed attempts |
| 12. Log | all | Timestamped activity log |

### Status Flow

```
created → issue → issue_done → design → design_done → plan → plan_done →
implement → implement_done → review → review_done → ship → shipped
```

Terminal states: `blocked`, `aborted`, `done`

## Project Setup

To use this runner in a new project:

1. Copy `scripts/skill-runner/` to your project
2. Create `.claude/skill-runner.conf` with your model config
3. Add project-specific skill files to `.claude/skills/<name>/SKILL.md`
4. Ensure you have a `CLAUDE.md` with project rules
5. Run: `scripts/skill-runner/skill-runner.sh <issue-number>`

## LLM Response Format

The LLM must produce output in this format for the parser to work:

```markdown
## Handoff Updates
<markdown to append/replace in handoff>

## Plan Updates
<markdown to append/replace in plan file>

## Code Changes
file: path/to/file.md
```
<new content>
```

create-file: path/to/new/file.md
```
<new content>
```

## Actions
- run: <command>
- read: <file path>
```

`file:` writes to an existing file. `create-file:` creates a new file (used by the issue skill to generate the handoff).

## Requirements

- Bash 4+
- git
- curl
- python3 (for JSON handling)
- gh CLI (optional, for GitHub operations)
- An LLM backend (local OpenAI-compatible API recommended)
