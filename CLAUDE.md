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
| `server/api.py` | FastAPI routes; auth via Bearer token; `/health`, `/pair`, `/games`, `/devices`, `/saves`, `/locks` |
| `server/store.py` | SQLite via stdlib `sqlite3`; tables: `devices`, `games`, `game_devices`, `saves`, `locks` |
| `server/config.py` | TOML config dataclass; load/save `~/.emusync/emusync.toml` |
| `server/mdns.py` | mDNS advertise + LAN discovery via `zeroconf` |
| `server/sync_client.py` | HTTP client wrapping all server endpoints (used by `emusync run`) |
| `gui/electron/main.ts` | IPC handlers; spawns/kills Python server; manages `serverProcess`, `serverToken`, PID file |
| `gui/electron/preload.ts` | `contextBridge` — everything in `window.emusync.*` is defined here |
| `gui/renderer/src/api.ts` | Fetch wrapper for the Python REST API; holds `_base` URL + `_token` |
| `gui/renderer/src/App.tsx` | Root component; screen router; auto-starts server if `is_server=true` |
| `gui/renderer/src/components/Setup.tsx` | First-launch onboarding (choose server or join) |
| `gui/renderer/src/components/ServerStatusButton.tsx` | Server control panel modal (start/stop, PIN, LAN discovery, re-pair) |
| `gui/renderer/src/components/GameList.tsx` | Main game list; play/edit/remove actions |
| `gui/renderer/src/components/GameConfig.tsx` | Add/edit game form with file pickers |

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
window.emusync.config.load()      // reads ~/.emusync/emusync.toml
window.emusync.config.save(data)  // writes config
window.emusync.config.exists()    // boolean

window.emusync.server.start()     // spawns emusync.py server start → { ok, token }
window.emusync.server.stop()      // SIGKILL server + pkill orphans + clean pid/token files
window.emusync.server.token()     // returns stored token (in-memory or from .server_token file)
window.emusync.server.changePin() // stops server, saves PIN, clears devices, restarts
window.emusync.server.discover()  // runs emusync.py server discover-json → server list

window.emusync.dialog.openFile()  // native file picker

window.emusync.game.launch(slug, command)  // spawns emusync run
window.emusync.game.stop()                 // SIGKILL game process group
window.emusync.game.isRunning()            // boolean
window.emusync.game.onExited(cb)           // subscribe to game:exited event
window.emusync.game.offExited(cb)          // unsubscribe
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

Config fields: `server_host`, `server_port`, `data_dir`, `device_id`, `device_name`, `token`, `is_server`, `server_pin` (optional).

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
make test   # runs tests/test_integration.py with pytest
```

Integration tests use a real SQLite DB (no mocks). They spin up the full store and API. Set `EMUSYNC_CONFIG_DIR` env var to isolate config between test runs.

**Do not mock the database.** The project had a past incident where mock/prod divergence masked a broken migration.

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

**Always do this before starting any new task:**

1. **Check open issues:** https://github.com/alekoHalkias/Emusync/issues
   Look for an existing issue that covers the work. If none exists, create one — it becomes the paper trail for why the change was made.

2. **Check open branches:** `git fetch --prune && git branch -r`
   Look for a branch already working on the same area. If one exists, coordinate before duplicating effort. Branches to watch: any `feature/*` or `copilot/*` branch touching the same files you intend to change.

3. **Name branches after the issue:** `feature/<issue-number>-short-description`
   Example: `feature/10-event-log`. This makes it trivial to trace a branch back to its rationale.

4. **Reference the issue in your PR/commit:** Use `Closes #N` in the PR body so GitHub auto-closes the issue on merge.

**Warning signs you should stop and check:**
- Another open branch modifies the same key file (e.g., two branches both touching `api.py` or `store.py`)
- An open issue already describes the problem you're about to solve
- An issue is assigned to someone else or has recent activity

---

## Active branches / conventions

- `main` — stable, release-ready
- Feature branches cut from `main`, merged via PR — named `feature/<issue-number>-description`
- The branch `feature/server-control-panel` contains the server modal UI and PIN system (not yet merged as of last update)
- No `--no-verify` or `--amend` on published commits

---

## Common gotchas

**Orphaned server processes** — If Electron exits abnormally, the uvicorn server can keep running. The stop handler uses three kill strategies (see Server process lifecycle above). If you see "port already in use", run: `pkill -9 -f "emusync.py server start"`.

**SIGKILL skips Python finally blocks** — `.server_pid` and `.server_token` files may not be cleaned up after a hard kill. The stop handler manually deletes them.

**WSL2 + Electron** — Requires `--no-sandbox` (baked into `npm run dev`). Needs `DISPLAY=:0` set. dbus errors in the output are harmless noise.

**Stale DB schema** — If you see `sqlite3.OperationalError: no such column`, delete `~/.emusync/emusync.db` and restart the server.

**TypeScript on `window.emusync`** — Typed as `any`; the global interface declaration is in `Setup.tsx`. If you add new IPC channels, add them there too or type errors won't surface at compile time.

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

A pre-commit hook (`.git/hooks/pre-commit`) warns when architecture files change without this file being updated. Run `bash install.sh` to install it.
