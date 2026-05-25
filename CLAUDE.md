# EmuSync — CLAUDE.md

## Project overview

EmuSync is a LAN save-file sync tool for emulators. One machine (gaming PC) runs a Python/FastAPI server. Other devices (Steam Deck, second PC) pair with it and sync saves automatically. The GUI is an Electron + React app that wraps the Python CLI. No cloud, no accounts, no port forwarding.

---

## Architecture

```
emusync.py          ← Click CLI entry point; all subcommands live here
server/             ← Python backend (FastAPI + SQLite + mDNS)
gui/electron/       ← Electron main process; spawns Python, bridges IPC
gui/renderer/src/   ← React renderer; talks to Python API via fetch + IPC
tests/              ← Integration tests (real SQLite, no mocks)
```

**Data flow:**
1. Electron spawns `emusync.py server start` as a child process
2. Python writes `~/.emusync/.server_pid` and `~/.emusync/.server_token` on start
3. Renderer calls Python REST API directly (`http://localhost:8765`) via `api.ts`
4. Electron IPC (`preload.ts` → `main.ts`) handles config I/O, server lifecycle, file dialogs, game launch
5. `emusync run` wraps emulator launch: pull save → launch → push save → release lock

---

## Key files

| File | Owns |
|------|------|
| `emusync.py` | All CLI subcommands (`server`, `device`, `game`, `run`, `sync`) |
| `server/api.py` | FastAPI routes; auth via Bearer token; `/health`, `/pair`, `/games`, `/devices`, `/whoami`, `/saves`, `/states`, `/locks`, `/events`, `/push-saves` |
| `server/store.py` | SQLite via stdlib `sqlite3`; tables: `devices`, `consoles`, `games` (device-specific), `saves` (global), `states` (global), `locks`, `events` |
| `server/config.py` | TOML config dataclass; load/save `~/.emusync/emusync.toml` |
| `server/mdns.py` | mDNS advertise + LAN discovery via `zeroconf` |
| `server/sync_client.py` | HTTP client wrapping all server endpoints (used by `emusync run`) |
| `gui/electron/main.ts` | IPC handlers; spawns/kills Python server; manages `serverProcess`, `serverToken`, PID file |
| `gui/electron/preload.ts` | `contextBridge` — everything in `window.emusync.*` is defined here |
| `gui/renderer/src/api.ts` | Fetch wrapper for the Python REST API; holds `_base` URL + `_token` |
| `gui/renderer/src/App.tsx` | Root component; screen router; auto-starts server if `is_server=true` |
| `gui/renderer/src/components/Setup.tsx` | First-launch onboarding (choose server or join) |
| `gui/renderer/src/components/ServerStatusButton.tsx` | Server control panel modal (start/stop, PIN, LAN discovery, re-pair) |
| `gui/renderer/src/components/DevicesButton.tsx` | Paired devices list modal (shows count, last sync times, delete button per device) |
| `gui/renderer/src/components/GameList.tsx` | Main game list; play/edit/remove actions; bulk delete with checkboxes |
| `gui/renderer/src/components/GameConfig.tsx` | Add/edit game form with file pickers |
| `gui/renderer/src/components/ConsoleImport.tsx` | "Add Console" wizard modal — console dropdown → emulator detection → ROM scan → import |

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

## IPC bridge

`preload.ts` exposes `window.emusync.*` via `contextBridge`. `main.ts` registers matching `ipcMain.handle` handlers.

**Current surface:**

```typescript
window.emusync.config.load()                          // reads ~/.emusync/emusync.toml
window.emusync.config.save(data)                      // writes config
window.emusync.config.exists()                        // boolean
window.emusync.config.getRecentFolders(consoleKey)   // returns string[] of recent ROM folders for console
window.emusync.config.addRecentFolder(consoleKey, path) // adds folder to recent list (keeps max 10)

window.emusync.server.start()     // spawns emusync.py server start → { ok, token }
window.emusync.server.stop()      // SIGKILL server + pkill orphans + clean pid/token files
window.emusync.server.token()     // returns stored token (in-memory or from .server_token file)
window.emusync.server.changePin() // stops server, saves PIN, clears devices, restarts
window.emusync.server.discover()  // runs emusync.py server discover-json → server list

window.emusync.dialog.openFile()  // native file picker
window.emusync.dialog.openFolder() // native folder picker

window.emusync.emulator.consoles()          // returns ordered console list { key, label }[] for the dropdown
window.emusync.emulator.detect(consoleKey)  // scans for installed emulators for that console; checks RetroArch (native+flatpak) cores + standalone emulators (mGBA etc.); resolves per-core save subfolder; returns { options: DetectedEmulatorOption[], suggestions[] }
window.emusync.emulator.scan(consoleKey, emulatorOption, extraPaths[])  // scans only that console's ROM extensions; uses emulatorOption.saveDir (already resolved to core subfolder); returns { emulators, romDirs, roms[] } with consoleName+coreName on each entry
window.emusync.files.ensureSave(path)       // creates an empty save file + parent dirs if the file doesn't exist; called during import for games with no existing save
window.emusync.files.getSaveTime(path)      // returns last modified time of save file as ISO string (YYYY-MM-DDTHH:MM:SS), or null if file doesn't exist

window.emusync.launcher.path()             // absolute path to emusync launcher binary

window.emusync.game.launch(game, command)  // spawns emusync run
window.emusync.game.stop()                 // SIGKILL game process group (in-app launches)
window.emusync.game.stopExternal()         // kill emulator + emusync via .game_pid file (Steam launches)
window.emusync.game.hasPidFile()           // true if .game_pid exists, process is alive, and cmdline contains emusync/python
window.emusync.game.isRunning()            // boolean
window.emusync.game.onExited(cb)           // subscribe to game:exited event
window.emusync.game.offExited(cb)          // unsubscribe

window.emusync.log.message(text)           // logs message to Electron main process (appears in make dev-gui terminal)
```

When adding a new IPC channel, add the handler to `main.ts` AND the bridge entry to `preload.ts`. The renderer's TypeScript sees `window.emusync` as `any` (no separate `.d.ts`) — the global type declaration lives in `Setup.tsx`.

---

## Config and data paths

| Path | Contents |
|------|----------|
| `~/.emusync/emusync.toml` | Per-device config (server host, port, token, is_server, server_pin) |
| `~/.emusync/emusync.db` | SQLite database (devices, games, saves, locks) |
| `~/.emusync/.server_pid` | PID of the running server process (written on start, deleted on clean exit) |
| `~/.emusync/.server_token` | Current pairing PIN (written on start, deleted on clean exit) |
| `~/.emusync/.game_pid` | Two-line file: line 1 = emusync run PID, line 2 = emulator child PID (written by `emusync run`, deleted on exit) |

Config fields: `server_host`, `server_port`, `data_dir`, `device_id`, `device_name`, `token`, `is_server`, `server_pin` (optional), `recent_import_folders` (dict mapping console keys to lists of recent folder paths).

---

## Server process lifecycle

- **Start:** `startServerProcess()` in `main.ts` spawns Python with `PYTHONUNBUFFERED=1`; reads `Pairing token: <value>` from stdout; stores in `serverToken` and `.server_token` file.
- **Stop:** SIGKILL `serverProcess` + read `.server_pid` and SIGKILL that PID + `pkill -9 -f "emusync.py server start"` to catch any orphaned processes. All three are needed: in-session reference, cross-session PID file, and pattern fallback.
- **App close:** `window-all-closed` does the same kill sequence before quitting.
- **Auto-start:** `App.tsx` calls `server.start()` on init if `is_server=true` in config.

---

## Authentication

- **Master token (PIN):** Set in `server_pin` config field. Used only during `/pair`. If empty, any device can pair without a code.
- **Device token:** UUID issued by `/pair`, stored in the client's config as `token`, sent as `Authorization: Bearer <token>` on all authenticated requests.
- Changing the PIN via `server:change-pin` IPC: clears all device records from the DB (they must re-pair), restarts the server.

---

## Testing

```bash
make test                          # run all tests
.venv/bin/python -m pytest tests/test_integration.py::test_name -v  # single test
```

Integration tests use a real SQLite DB (no mocks). They spin up the full store and API via `httpx.AsyncClient` + `ASGITransport`. Set `EMUSYNC_CONFIG_DIR` env var to isolate config between test runs.

**Do not mock the database.** The project had a past incident where mock/prod divergence masked a broken migration.

### Claude agents — testing requirements

**Before marking any task complete, run `make test` and confirm it passes.**

When adding or changing code, write tests if any of the following are true:

- You added a new API route (`server/api.py`) → add an integration test for the happy path and the main error case (404, 403, 409, etc.)
- You added a new `Store` method (`server/store.py`) → test it directly via `Store(tmpdir)` or through the API
- You added a CLI subcommand (`emusync.py`) → note it in the PR; CLI-level tests are optional but preferred for logic-heavy commands
- You fixed a bug → add a regression test that would have caught it

**How to write a test** — follow the pattern in `tests/test_integration.py`:

```python
@pytest.mark.asyncio
async def test_your_scenario(client):          # client fixture = fresh DB + app
    token = await _pair(client)               # pair a device to get a bearer token
    auth = {"Authorization": f"Bearer {token}"}
    r = await client.post("/your-route", json={...}, headers=auth)
    assert r.status_code == 200
```

For tests that need blank-PIN (open access) or direct store access, spin up your own fixture:

```python
with tempfile.TemporaryDirectory() as tmpdir:
    store = Store(tmpdir)
    api_module.init(store, "")   # blank = open access
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
3. GitHub Actions (`release.yml`) triggers:
   - Runs tests
   - Builds Linux AppImage on `ubuntu-latest`
   - Builds Windows NSIS installer on `windows-latest`  
   - Publishes a GitHub Release with both artifacts

Artifact naming: `EmuSync-{version}-linux-x86_64.AppImage` and `EmuSync-{version}-windows-x64-setup.exe`.

To re-cut a failed release: delete the tag remotely and locally, fix the issue, re-tag.

---

## Development workflow — before touching code

**This applies to both human developers and Claude Code agents. Claude: do not start writing or editing code until these steps are complete.**

### Step 1 — find or create an issue

```bash
curl -s "https://api.github.com/repos/alekoHalkias/Emusync/issues?state=open&per_page=50"
```

Read the list. If an existing issue covers the requested work, use it. If not, create one via the GitHub UI or API before proceeding. The issue is the paper trail for why a change was made.

**Claude agents:** if the user gives you a task without mentioning an issue, check the list yourself. If no issue matches, tell the user what issue you'd create and ask them to confirm before you create it (issue creation is visible to the whole team). If they confirm, create it using the method below and note the issue number.

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

**Always prefix gh commands with `export PATH="$HOME/.local/bin:$PATH"` in this project** until it's on the system PATH.

### Step 2 — check for conflicting branches

```bash
git fetch --prune && git branch -r
```

Look for any `feature/*` or `copilot/*` branch that is likely to touch the same files. If one exists, stop and flag it to the user before writing any code — two branches editing `api.py` or `store.py` simultaneously will produce a painful merge.

### Step 3 — create a linked branch

Name the branch after the issue: `feature/<issue-number>-short-description`

```bash
git checkout main && git pull && git checkout -b feature/10-event-log
```

**Claude agents:** if the user is already on a correctly-named branch, skip this. If they're on `main` or an unlinked branch, create the right branch before making any edits.

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
- The branch `feature/server-control-panel` contains the server modal UI and PIN system (merged into main)
- No `--no-verify` or `--amend` on published commits

---

## State File Syncing (NEW)

In addition to save files (SRAM), EmuSync now syncs **save states** (snapshots). RetroArch stores these in `states/<CoreName>/game.state` parallel to `saves/<CoreName>/game.sav`. State syncing mirrors save syncing at every layer:

- **DB schema**: new `states` table; `state_path` column added to `game_devices` via migration
- **API**: new `/games/{game}/state` routes (GET/POST) and `/games/{game}/state/meta`
- **CLI (`emusync run`)**: pulls state before launch, pushes after exit (opt-in if `state_path` is configured); auto-detects actual save/state file extensions and updates config if needed
- **Electron**: detects `savestate_directory` from `retroarch.cfg`, scans for `.state` / `.state.auto` files per ROM
- **GUI**: wizard shows `✓ State found` / `⊕ State will be created` badges; does not pre-create files, only tracks paths

State sync is **opt-in** — if a game's `state_path` is empty, it is skipped silently. The scan handler checks both the per-core subfolder and the root `states/` dir for backwards compatibility with pre-existing states.

**Auto-detection of save/state file extensions** — During import, games are registered with a default save/state path (e.g., `saves/SNES/game.sav`), but the actual extension emulator writes may differ (e.g., `.srm`). After the emulator exits in `emusync run`, the wrapper scans the save/state directory for files with the same base name but different extensions. If found, the game config is automatically updated with the correct path, and subsequent plays will sync the correct file. No manual path editing needed.

---

## ROM Folder Tracking

During console import, the `rom_folder_path` is extracted from each ROM file path and saved with the game config. This allows:
- Future features to re-scan specific folders for game updates
- Tracking which folder contained each game's ROM file
- Managing multiple games from the same directory

The path is extracted from the full ROM file path during import and returned by `GET /games/{game}/device` endpoint alongside `rom_path`, `save_path`, `state_path`, and `launch_command`.

---

## Games Table Architecture (Device-Specific)

Games are now stored with **device scope** — each device maintains its own copy of a game record with (game, device_id) as the primary key. This allows:
- Each device to configure its own ROM path, save path, launch command, state path
- Per-device sync metadata (last_synced_at, sync_state, local_save_time, remote_save_time)
- Per-device game metadata (added_at, last_played_at, enabled)

**Saves and states remain global** — they are shared across all devices and stored by game ID only (not keyed per-device). When device A syncs a save, device B can pull it even if device B hasn't imported the game locally yet.

**Locks are per-device** — a lock is (game, device_id), so multiple devices can each hold a lock on the same game without conflict.

---

## Debug tools

```bash
# Scan a folder for ROMs from the CLI (no Electron needed)
node scripts/scan-roms.mjs <folder> [--ext gba,sfc] [--depth 3] [--verbose]

# Example: find all GBA ROMs up to 3 dirs deep
node scripts/scan-roms.mjs ~/Games/GBA --ext gba --verbose
```

The `emulator:scan` IPC handler emits `[scan]` lines to stderr when running in
dev mode — visible in the `make dev-gui` terminal.

---

## Common gotchas

**Orphaned server processes** — If Electron exits abnormally, the uvicorn server can keep running. The stop handler uses three kill strategies (see Server process lifecycle above). If you see "port already in use", run: `pkill -9 -f "emusync.py server start"`.

**SIGKILL skips Python finally blocks** — `.server_pid` and `.server_token` files may not be cleaned up after a hard kill. The stop handler manually deletes them.

**WSL2 + Electron** — Requires `--no-sandbox` (baked into `npm run dev`). Needs `DISPLAY=:0` set. dbus errors in the output are harmless noise.

**Stale DB schema** — If you see `sqlite3.OperationalError: no such column`, delete `~/.emusync/emusync.db` and restart the server.

**TypeScript on `window.emusync`** — Typed as `any`; the global interface declaration is in `Setup.tsx`. If you add new IPC channels, add them there too or type errors won't surface at compile time.

**RetroArch config paths use `~` which Node.js does not expand** — `retroarch.cfg` commonly stores paths like `savefile_directory = "~/.config/retroarch/saves"`. `parseRetroArchCfg` in `main.ts` expands leading `~/` to the real home directory so that `existsSync`, `mkdirSync`, and `join` work correctly. Do not call `parseRetroArchCfg` without passing `home` and do not use raw config values as filesystem paths without checking for tilde. Also, `rgui_browser_directory = "default"` is RetroArch's placeholder for "not configured" — it is filtered out and never passed as a ROM directory.

**RetroArch per-core save directory is always `saves/<CoreName>/`** — `detectEmulatorsForConsole` uses `join(ra.saveDir, core.folderName)` unconditionally. The old `resolveCoreSaveDir` fell back to the root saves dir if the subfolder did not exist yet, causing saves to land in the wrong place on fresh installs. The scan handler additionally checks the root saves dir as a fallback when looking for *existing* saves written before per-core organisation was set up.

**`store.add_game` uses UPDATE for existing games** — `add_game(game)` checks if the game record already exists and uses UPDATE instead of INSERT OR REPLACE to preserve associated saves and locks. Use `update_game_name(game, device_id, name)` to rename an existing game.

**Game import logging** — When games are imported via the GUI, a `[IMPORT]` line is logged to the Electron console (developer tools) for each game with all game record data (game ID, device_id, name, console, rom_path, save_path, launch_command, state_path, rom_folder_path). This is useful for debugging import issues and verifying correct path detection. The logs appear in the `make dev-gui` terminal output.

**Duplicate-launch guard in `emusync run`** — Before acquiring the lock, the wrapper checks the lock state. If the lock is already held (by this device or another), it calls `_show_game_running_popup` which displays "\<game\> is already running. Please close it on \<device\>." and then exits. The popup uses a subprocess fallback chain — `notify-send` → `zenity` → `kdialog` → `xmessage` → tkinter — so it works on Wayland, X11, Steam Deck Gaming Mode (gamescope), and environments where `libtk` may not be installed. `notify-send` fires first and is non-blocking (auto-dismisses); the chain then continues to the first available blocking dialog so desktop users still get a modal. The race-condition path (409 from `acquire_lock`) follows the same flow.

---

## Keeping this file updated

Update this file when any of the following change:

- CLI subcommands added or removed (`emusync.py`)
- IPC channels added or removed (`main.ts` / `preload.ts`)
- New React components added to `gui/renderer/src/components/`
- Config fields added or removed (`server/config.py`)
- New data files written to `~/.emusync/`
- Python or Node dependency changes (`requirements.txt`, `package.json`)
- Release or CI/CD process changes
- Changes to `install.sh`, `Makefile`, or `emusync-server.service`

A pre-commit hook (`.git/hooks/pre-commit`) warns when architecture files change without this file being updated. Run `bash install.sh` to install it.
