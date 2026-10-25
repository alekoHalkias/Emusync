# Backend Design Guide

## EmuSync Patterns

### API Routes
- One FastAPI APIRouter per domain (auth, games, consoles, sync, transfer, watch, run, rom, mod)
- Route files: `server/api/<domain>.py`
- Auth: Bearer token (PIN) + device headers (X-Device-ID, X-Device-Name)
- Response: JSON with status codes; errors as `{"error": "message"}`

### Store Methods
- SQLite with stdlib, WAL mode
- Schema in `server/store/schema.py` (PRAGMA user_version)
- Migrations: `from_version < N` in `_migrate()`, bump `_SCHEMA_VERSION`, update `_SCHEMA`
- Mixins: one per table group in `server/store/mixins/`
- No mocks in tests — real SQLite only

### CLI Commands
- Grouped by domain: `server`, `device`, `game`, `console`, `sync`, `transfer`, `watch`, `run`, `rom`, `mod`
- Entry: `emusync.py` thin CLI shim
- No emojis in CLI output

### Sync Logic
- Conflict = both sides moved past device's `save_sync_baseline`
- Blobs carry transfer envelope (`_pack_envelope`/`_unpack_envelope`)
- Hash envelope-free (`_memcard_payload_bytes`), never hash `memcard_bytes()`
- Shared-memcard flag is DB-backed, sourced from `consoles_data.py` — never re-hardcode

### Config
- TOML via tomlkit: `emusync.toml`
- GUI-only settings: `display.json` (not in TOML)
- Atomic writes + 0600 permissions
- Corrupt TOML renamed `.corrupt-<ms>`

### Paths
- XDG dirs via `server/paths.py` / `gui/electron/paths.ts`
- `EMUSYNC_*_DIR` env vars disable migration

## Workflow-CLI Patterns

### Project Config (`.workflow-cli/config.yaml`)
- YAML structure with: project info, LLM settings, skill paths, rule files, test/lint commands, hooks
- Discovered by walking up from CWD for `.workflow-cli/config.yaml`
- No hardcoded repo knowledge — fully project-agnostic

### State Management
- Handoff file: `plans/<N>-handoff.md` (12-section template, Markdown)
- Runtime state: `.workflow-cli/state.json` (JSON with run history, LLM usage, timing)
- Atomic writes for all state files

### Action Format
- LLM returns JSON: `{actions: [{id, type, params}], output, needs_user_input}`
- Action types: bash, gh, read, write, edit, ask_user, approve, skip, error
- CLI executes actions in order, feeds results back to LLM

### Skill Loading
- Skills from configurable `skills_dir` (e.g., `.claude/skills/`)
- Each skill: directory with `SKILL.md`
- Prompt assembly: system prompt + skill instructions + project rules + handoff + plan + code context

### Stage Transitions
- Handoff status drives next skill: created → designed → planned → implementing → implemented → shipped/blocked
- Gates at plan ready and ship ready (user approval required)
