# EmuSync — CLAUDE.md

## Project overview

EmuSync is a LAN save-file sync tool for emulators: one machine (gaming PC) runs a Python/FastAPI server, other devices (Steam Deck, second PC) pair with it and sync saves automatically. GUI is Electron + React wrapping the Python CLI. No cloud, no accounts, no port forwarding.

For the exhaustive module-by-module reference (every file's full responsibilities, the complete IPC surface, config/data paths, server lifecycle, auth, state syncing, ROM transfer protocol) see **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — read it on demand when working in the relevant area, don't load it speculatively.

---

## Architecture

```
emusync.py          ← Thin CLI entry-point shim (kept at this path for install.sh/Makefile/Electron spawn/pkill); delegates to the cli/ package
cli/                ← Click CLI implementation; one module per command group
server/             ← Python backend (FastAPI + SQLite + mDNS)
gui/electron/       ← Electron main process; spawns Python, bridges IPC
gui/renderer/src/   ← React renderer; talks to Python API via fetch + IPC
tests/              ← Integration tests (real SQLite, no mocks)
```

**Data flow:**
1. Electron spawns `emusync.py server start` as a child process
2. Python writes `~/.emusync/.server_pid` and `.server_token` on start
3. Renderer calls the Python REST API (`http://localhost:8765`) directly via `api.ts`
4. Electron IPC (`preload.ts` → `main.ts`) handles config I/O, server lifecycle, file dialogs, game launch
5. `emusync run <slug>` wraps emulator launch: derives the emulator command from the game's stored `launch_command`, reconciles the save (push if local newer than server, else pull) → launch → push save → release lock. If the server is unreachable, launch proceeds **offline** and the play window is logged so a newer offline save wins the next online launch. A true divergence auto-resolves newest-wins, surfaced via stderr + a desktop notification + `save_conflicts.json`

---

## Key files

| Path | Owns |
|------|------|
| `emusync.py` | Thin entry-point shim — bootstraps `sys.path`, calls `cli()`. Must stay at this exact path (referenced by `install.sh`/`Makefile`/Electron `spawn`/`pkill`) |
| `cli/` | Click CLI, one module per command group: `server`/`device`/`game`/`console`/`sync`/`transfer`/`watch`/`run`/`rom`. `consoles_data.py`/`detect.py` drive emulator/core detection for the import wizard (mirrors `gui/electron/emulator/detect.ts`) |
| `server/api/` | FastAPI app, one `APIRouter` per domain (`devices`/`games`/`transfers`/`blobs`/`locks`/`defs`/`conflicts`/`settings`). PIN + device-header auth |
| `server/store/` | SQLite (stdlib `sqlite3`, WAL), one CRUD mixin per table-group; schema versioned via `PRAGMA user_version` in `schema.py` |
| `server/config.py` | TOML config dataclass; load/save `~/.emusync/emusync.toml` |
| `server/mdns.py` | mDNS advertise + LAN discovery via `zeroconf` |
| `server/sync_client.py` | HTTP client wrapping all server endpoints, used by `emusync run`/`push`/`pull` |
| `gui/electron/` | Electron main process, per-domain modules (`server.ts`, `game.ts`, `sync/*.ts`, `emulator/*.ts`, `steam.ts`, `art.ts`, `steamgriddb.ts`, `artwork.ts`). Shared mutable state lives on the `rt` object in `runtime.ts` |
| `gui/electron/preload.ts` | `contextBridge` — everything in `window.emusync.*` is defined here |
| `gui/renderer/src/api.ts` | Fetch wrapper for the Python REST API |
| `gui/renderer/src/components/` | React components — `App.tsx` (router), `ConsoleGrid`/`GameGrid`/`GameCard` (browse), `GameModal`/`GameConfig`/`ArtworkTab`/`SaveHistory` (per-game), `ConsoleImport` + `console-import/` (Add Console wizard), `ServerStatusButton`/`DevicesButton`/`ConflictsButton` (server controls) |

---

## Development commands

```bash
# Full install (run once after cloning)
bash install.sh

# Start Python server manually
make dev-server                  # uses .venv/bin/python

# Start GUI (dev mode with hot reload)
make dev-gui                     # cd gui && npm run dev

# Run tests
make test                        # pytest tests/ -v

# Lint Python
make lint                        # syntax check only (py_compile)

# Build GUI for distribution
make build-gui                   # electron-vite build

# Cut a release (tags + pushes, triggers GitHub Actions)
make release VERSION=v1.2.3

# Install / remove the systemd user service (Steam Deck / headless server)
make install-service             # generates service file, enables + starts it
make uninstall-service           # disables + removes it
```

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| CLI | Python 3.10+, Click |
| API server | FastAPI + uvicorn |
| Database | SQLite (stdlib `sqlite3`, WAL mode) |
| Service discovery | zeroconf (mDNS) |
| Config | TOML via `tomlkit` |
| GUI shell | Electron 31 |
| GUI framework | React 18 + TypeScript |
| GUI build | electron-vite + Vite 5 |
| HTTP client (renderer) | native `fetch` |
| HTTP client (Python) | httpx |

---

## Testing

```bash
make test                          # run all tests
.venv/bin/python -m pytest tests/test_integration.py::test_name -v  # single test
```

Integration tests use a real SQLite DB (no mocks), spinning up the full store and API via `httpx.AsyncClient` + `ASGITransport`. Set `EMUSYNC_CONFIG_DIR` to isolate config between test runs.

**Do not mock the database.** Past incident: mock/prod divergence masked a broken migration.

### Claude agents — testing requirements

**Before marking any task complete, run `make test` and confirm it passes.**

Write tests when:
- You added a new API route (relevant `server/api/` router) → integration test for the happy path + main error case (404/403/409/etc.)
- You added a new `Store` method (relevant `server/store/` mixin) → test via `Store(tmpdir)` or through the API
- You added a CLI subcommand (`cli/` package) → note it in the PR; tests optional but preferred for logic-heavy commands
- You fixed a bug → add a regression test that would have caught it

**How to write a test** — follow the pattern in `tests/test_integration.py`:

```python
MASTER_PIN = "test-master-pin"
AUTH = {
    "Authorization": f"Bearer {MASTER_PIN}",
    "X-Device-ID": "device-abc",
    "X-Device-Name": "test-pc",
}

@pytest.mark.asyncio
async def test_your_scenario(client):          # client fixture = fresh DB + app
    r = await client.post("/your-route", json={...}, headers=AUTH)
    assert r.status_code == 200
```

Multi-device tests / custom PINs:

```python
def _device_auth(device_id: str, device_name: str, pin: str) -> dict:
    return {
        "Authorization": f"Bearer {pin}",
        "X-Device-ID": device_id,
        "X-Device-Name": device_name,
    }

# Device 1 and 2 both connect with same PIN
auth1 = _device_auth("d1", "PC", MASTER_PIN)
auth2 = _device_auth("d2", "Steam Deck", MASTER_PIN)
```

Blank-PIN (open access) or direct store access:

```python
with tempfile.TemporaryDirectory() as tmpdir:
    store = Store(tmpdir)
    api_module.init(store, "")   # blank PIN = open access
    async with AsyncClient(transport=ASGITransport(app=api_module.app), base_url="http://test") as c:
        ...
```

**Never use mocks.** Real SQLite only.

---

## Release process

```bash
make release VERSION=v1.2.3
```

1. Creates a git tag locally
2. Pushes the tag to origin
3. GitHub Actions (`release.yml`) triggers: runs tests, builds a Linux AppImage on `ubuntu-latest`, builds a Windows NSIS installer on `windows-latest`, publishes a GitHub Release with both artifacts

Artifact naming: `EmuSync-{version}-linux-x86_64.AppImage`, `EmuSync-{version}-windows-x64-setup.exe`.

To re-cut a failed release: delete the tag remotely and locally, fix the issue, re-tag.

---

## Execution approval policy

Applies to every Claude agent and skill working in this repo (`/issue`, `/plan`, `/implement`, and any added later):

- Read-only commands (curl GET, `gh issue/pr list|view`, `git status|log|branch|fetch|diff`, `make test`, lint/build checks) always run automatically — never pause to ask first.
- GitHub issue creation, PR creation, and git commits/pushes are pre-approved — create/commit/push/open-PR without asking "should I proceed?".
- Only pause for the user's explicit go-ahead when a step would directly modify something on the machine *outside* this repo (e.g. deleting unrelated files, changing system config, killing unrelated processes). Editing tracked files, opening a PR, or filing an issue does not require a pause.
- Clarifying questions about ambiguous requirements are not permission requests — always fine to ask those.

---

## Development workflow — before touching code

**Applies to both human developers and Claude Code agents. Claude: do not start writing or editing code until these steps are complete.**

Automated path: the `/issue`, `/plan`, and `/implement` skills (`.claude/skills/`) run Steps 1–4 below end to end — `/issue` finds-or-files the issue and cuts the branch, `/plan` reads it and drafts an implementation plan, `/implement` executes the plan and opens the PR. The manual steps below are the reference for what those skills automate, and the fallback for ad-hoc work outside that pipeline.

### Step 1 — find or create an issue

```bash
curl -s "https://api.github.com/repos/alekoHalkias/Emusync/issues?state=open&per_page=50"
```

Read the list. If an existing issue covers the work, use it; if not, create one before proceeding — it's the paper trail for why a change was made.

**Claude agents:** if given a task without an issue mentioned, check the list yourself. If none matches, create one directly using the method below and note the issue number — see Execution approval policy above, issue creation needs no confirmation pause.

#### How Claude agents create issues

Check for tools in this order:

```bash
# 1. Preferred — gh CLI (handles auth transparently)
which gh && gh issue create --repo alekoHalkias/Emusync --title "..." --body "..."

# 2. Fallback — curl with GITHUB_TOKEN env var
curl -s -X POST https://api.github.com/repos/alekoHalkias/Emusync/issues \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  -d '{"title":"...","body":"..."}'
```

If neither works (no `gh`, no `GITHUB_TOKEN`), tell the user:
> "I need GitHub access to create the issue. Run `gh auth login` or set `GITHUB_TOKEN=<your PAT>` in your shell, then ask again."

To set up `gh` on this machine (WSL2/Linux):
```bash
curl -sL https://github.com/cli/cli/releases/download/v2.71.0/gh_2.71.0_linux_amd64.tar.gz \
  | tar xz -C /tmp && mkdir -p ~/.local/bin && mv /tmp/gh_2.71.0_linux_amd64/bin/gh ~/.local/bin/gh
export PATH="$HOME/.local/bin:$PATH"   # add to ~/.bashrc to persist
gh auth login
```

### Step 2 — check for conflicting branches

```bash
git fetch --prune && git branch -r
```

Look for any `feature/*` or `copilot/*` branch likely to touch the same files. If one exists, stop and flag it before writing any code — two branches editing `api.py` or `server/store/` simultaneously produces a painful merge.

### Step 3 — create a linked branch

Name the branch after the issue: `feature/<issue-number>-short-description`

```bash
git checkout main && git pull && git checkout -b feature/10-event-log
```

**Claude agents:** skip this if already on a correctly-named branch. If on `main` or an unlinked branch, create the right one before making any edits.

### Step 4 — reference the issue in the PR

Use `Closes #N` in the PR body so GitHub auto-closes the issue on merge.

---

**Stop and warn the user if:**
- Another open branch is already modifying the same key files
- An open issue is assigned to someone else or has recent activity suggesting active work
- The current branch name has no issue number and `--no-verify` would be needed to commit

---

## Active branches / conventions

- `main` — stable, release-ready
- Feature branches cut from `main`, merged via PR — named `feature/<issue-number>-description`
- No `--no-verify` or `--amend` on published commits

---

## Debug tools

```bash
# Scan a folder for ROMs from the CLI (no Electron needed)
node scripts/scan-roms.mjs <folder> [--ext gba,sfc] [--depth 3] [--verbose]

# Example: find all GBA ROMs up to 3 dirs deep
node scripts/scan-roms.mjs ~/Games/GBA --ext gba --verbose
```

The `emulator:scan` IPC handler emits `[scan]` lines to stderr in dev mode — visible in the `make dev-gui` terminal.

---

## Common gotchas

**Shared-save-layout consoles (PS2/DC/GC/PSP) — never treat the save as per-game.** For consoles where the save lives in ONE shared location across every game, the per-game save must not be renamed, moved, or pushed per-game; it syncs as a console-scoped card via `/consoles/{key}/memcard` + `emusync run`'s `_MemcardClient`. Card paths resolve at import (first existing candidate wins): PS2 `memcards/Mcd001.ps2`; Dreamcast `saves/vmu_save_A1.bin` (slot A1 only); GameCube/Wii Dolphin's `User/GC` folder (Wii NAND title saves NOT synced); PSP `PPSSPP/PSP/SAVEDATA` folder (all games one blob). **Save STATES are a separate axis**: only PS2 shares states (serial-named `sstates/`) — dc/gamecube/psp cores write normal per-content states with full per-game sync. Renderer gates: `usesSharedSaveLayout` (all four) vs `usesSharedStateLayout` (`{ps2}` only) in `console-import/helpers.ts`. CLI mirror: `run_ps2.py`'s `_SHARED_MEMCARD_CONSOLES`/`_SHARED_STATE_CONSOLES` and `scan.ts`'s equivalents. Keep all in sync if adding a shared-layout console.

**Orphaned server processes** — If Electron exits abnormally, uvicorn can keep running. "Port already in use": run `pkill -9 -f "emusync.py server start"`. `emusync server start` now detects a running server and exits gracefully instead of duplicating it.

**SIGKILL skips Python finally blocks** — `.server_pid`/`.server_token` may survive a hard kill; the stop handler manually deletes them.

**WSL2 + Electron** — requires `--no-sandbox` (baked into `npm run dev`) and `DISPLAY=:0`. dbus errors in the output are harmless.

**Stale DB schema** — `sqlite3.OperationalError: no such column` → delete `~/.emusync/emusync.db` and restart the server.

**TypeScript on `window.emusync`** — globally typed via `EmusyncBridge` in `gui/renderer/src/emusync.d.ts`, the source of truth mirroring `preload.ts`. New IPC channel → add its signature there too, or renderer call sites won't be type-checked.

**RetroArch config paths use `~`, which Node.js doesn't expand** — `parseRetroArchCfg` expands leading `~/` to the real home dir so `existsSync`/`mkdirSync`/`join` work. Always pass `home`; never use a raw config value as a filesystem path without checking for tilde. `rgui_browser_directory = "default"` is RetroArch's "not configured" placeholder — filtered out, never passed as a ROM directory.

**RetroArch per-core save directory is always `saves/<CoreName>/`** — `detectEmulatorsForConsole` uses `join(ra.saveDir, core.folderName)` unconditionally. The scan handler still checks the root dir as a fallback when looking for *existing* saves written before per-core organisation.

**RetroArch "Sort saves/states by content directory"** — canonical model: saves at `savesRoot/GameName/GameName.srm`, states as a FOLDER at `statesRoot/GameName/` (all slots live there). `state_path` stores the FOLDER, not a file. Both push/pull detect a directory `state_path` and pack/extract all files as a **tar.gz**. **State pulls are non-destructive:** the folder extractor backs up every overwritten file to `.bak` and *retains* it. Push **excludes `.bak` files** so backups never propagate.

**`store.add_game` is INSERT OR IGNORE, not INSERT OR REPLACE** — only inserts new rows, never overwrites. Use `update_game_name(slug, name)` to rename.

**Duplicate-launch guard in `emusync run`** — before acquiring the lock, if it's already held, `_show_game_running_popup` shows a message and exits. Fallback chain — `notify-send` → `zenity` → `kdialog` → `xmessage` → tkinter — works across Wayland, X11, Steam Deck Gaming Mode, and environments missing `libtk`.

**DB thread safety — one connection per thread, not shared** — `server/store/connection.py`'s `_ThreadLocalConnection` lazily creates one `sqlite3.Connection` per thread. The store is hit from uvicorn's worker-thread pool *and* the presence-monitor daemon thread; a shared connection can't handle concurrent cursor access safely. `PRAGMA foreign_keys` is per-connection — set on every connection in the factory. Don't reintroduce a shared connection guarded by a lock that releases before fetch.

**DB schema versioning — use `PRAGMA user_version`, not try/except** — `server/store/schema.py` tracks the version in `PRAGMA user_version`. Adding a migration: (1) add an `if from_version < N:` block in `_migrate()`, (2) bump `_SCHEMA_VERSION`, (3) add the new table/column to `_SCHEMA` so fresh DBs get it without migrating. **Fresh DBs are stamped with `PRAGMA user_version = _SCHEMA_VERSION`** right after `_SCHEMA` is applied — don't remove that stamp, or every new install re-runs the whole migration chain against the schema it just created.

**`config:load` returns `null` when config is absent** — both when the TOML file is missing and when it fails to parse. Check for `null` rather than calling the separate `config:exists` first.

**mDNS runs in a background thread** — `daemon=True` so the pairing token prints without waiting on socket/network probing. The `finally` block joins the thread (2s timeout) before unregistering the service.

**Token is printed before uvicorn binds** — code calling `server.start()` and immediately hitting the API will get connection refused — always poll `/health` first.

**Blank PIN servers must match in the token regex** — `startServerProcess` looks for `Pairing token: (\S*)` (zero-or-more, not `\S+`), since a blank PIN prints `"Pairing token: "` with no value.

**Electron main process must use `fetch`, not `http.get`** — `sync.ts`/`steamgriddb.ts` establish `fetch()` as the main-process pattern. The renderer process also uses normal `fetch()`.

**`server_host` is empty string on server devices** — they store `server_host = ""` since they connect to themselves. Fall back to `"localhost"` when empty; never use `!cfg.server_host` as a "not configured" guard — check `!cfg.server_port` instead.

---

## Keeping this file updated

Update **CLAUDE.md** when the execution policy, dev workflow, or a gotcha changes. Update **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** when:
- CLI subcommands, IPC channels, or React components are added/removed
- Config fields or new `~/.emusync/` data files are added/removed
- Server lifecycle, auth, or the ROM transfer protocol changes

A pre-commit hook (`.git/hooks/pre-commit`) warns when architecture files change without docs being updated. Run `bash install.sh` to install it.
