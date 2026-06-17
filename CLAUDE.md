# EmuSync — CLAUDE.md

## Project overview

EmuSync is a LAN save-file sync tool for emulators. One machine (gaming PC) runs a Python/FastAPI server. Other devices (Steam Deck, second PC) pair with it and sync saves automatically. The GUI is an Electron + React app that wraps the Python CLI. No cloud, no accounts, no port forwarding.

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
2. Python writes `~/.emusync/.server_pid` and `~/.emusync/.server_token` on start
3. Renderer calls Python REST API directly (`http://localhost:8765`) via `api.ts`
4. Electron IPC (`preload.ts` → `main.ts`) handles config I/O, server lifecycle, file dialogs, game launch
5. `emusync run <slug>` wraps emulator launch — it takes the game slug and derives the emulator command from the game's stored `launch_command`: reconcile save (push if local is newer than the server, else pull) → launch → push save → release lock. As a fallback for the old method, an explicit command may still be passed (`emusync run <slug> -- retroarch …`, e.g. a Steam `%command%` wrapper around RetroArch's own launcher); that command is honored **only if the game is imported** on this device (has a `save_path`), so EmuSync can sync it — otherwise the launch is refused. A true divergence (both copies changed) is auto-resolved newest-wins and surfaced via stderr + a `notify-send` desktop notification + an entry in `save_conflicts.json`. If the server is unreachable it launches **offline** (no lock/sync) and appends the play window to `offline_plays.json` so a newer offline save wins the next online launch (issue #5)

---

## Key files

| File | Owns |
|------|------|
| `emusync.py` | Thin entry-point shim: bootstraps `sys.path` and calls `cli()` from the `cli/` package. Must stay at this path/filename — `install.sh`, the `Makefile`, the Electron `spawn` in `main.ts`, and `pkill -f "emusync.py server start"` all invoke it by path. No command logic lives here |
| `cli/` | Click CLI implementation, one module per command group. `cli/root.py` defines the root `cli` group; `cli/__init__.py` imports every command module (registering subcommands) and re-exports `cli`. `cli/common.py` = shared helpers (`_client`, `_print_table`, `_get_device_name`, `_show_game_running_popup`, and `_fmt_time`/`_relative`/`_parse_iso_utc` for human-readable timestamps — issue #216); `cli/consoles_data.py` = hardcoded `_IMPORT_CONSOLES`/`_IMPORT_SYSTEMS`/extension sets + `_prepare_console_seed_data` (seeds the server's global console defs); `cli/detect.py` = RetroArch/core/ROM detection + scan helpers (mirrors `main.ts`); `cli/server.py` = `server` group (start/stop/restart/clear-devices/discover-json) + lifecycle helpers + embedded transfer daemon; `cli/device.py` = `device` group (`connect`/`list`/`compare`, where `compare` shows game coverage across paired devices); `cli/game.py` = `game` group (`add`/`list`/`edit`/`remove`); `cli/console.py` = `console` group (`list` + `import`, the interactive wizard mirroring the GUI Add Console flow: detect RetroArch/cores/standalones → scan ROM folder → bulk import); `cli/sync.py` = `sync status` + `sync history <slug>` / `sync restore <slug> <version-id>` (save/state rollback, issue #7 — `--state` flag targets states; restore makes the chosen version current on the server and writes it to this device's disk if configured); `cli/transfer.py` = top-level `push`/`pull`/`sync-daemon` + the transfer daemon loop (`push` streams a ROM to a target device; `pull` requests a ROM from a source device via a pull request the source's sync-daemon fulfills; `sync-daemon` holds an SSE connection open, auto-receives incoming transfers, and fulfills pending pull requests); `cli/run.py` = `run` command + the SIGTERM handler that kills the emulator child (registered at import time). Before launch it reconciles the save via `_reconcile_save`/`_decide_save_action` (newest-wins: push if local mtime > server `pushed_at`, pull otherwise, loser kept as `.bak`); a true divergence is surfaced via `_warn_save_conflict` (stderr + `_notify` desktop notification + `_log_save_conflict` → `save_conflicts.json`). After the game exits, the post-game save push is gated by `_save_is_safe_to_push` (issue #213): a 0-byte save, or one that shrank below 50% of the server's previous copy (a truncation signal from a crashed emulator), is **not** pushed — the good server copy is kept and the refusal is surfaced via `_warn_unsafe_save` (stderr + notification). If `client.health()` fails it falls back to `_run_offline` — launches anyway and logs the play to `offline_plays.json`; `_cache_game_device`/`_load_cached_game_device` persist each game's paths under `game_cache/` so offline launches know the save path (the authoritative config lives on the server) |
| `server/api.py` | FastAPI routes; auth via `Authorization: Bearer {PIN}` + `X-Device-ID`/`X-Device-Name` headers; `/health`, `/games`, `/games/overview` (per-device batch: every game's lock + last save + this device's config in one call — registered before `/games/{slug}` so it isn't matched as a slug; used by the GUI game list + lock poll instead of fanning out 3 requests per game), `/devices`, `/whoami`, `/saves`, `/states`, `/locks`, `/events`, `/events/stream` (SSE), `/games/{slug}/devices`, `/game-devices`, `/devices/{id}/consoles`, `/devices/{id}/game-devices`, `/games/{slug}/rom-transfer`, `/rom-transfers/pending`, `/rom-transfers/{id}/file`, `/rom-transfers/{id}`, `/games/{slug}/rom-pull-request`, `/rom-pull-requests/pending`, `/rom-pull-requests/{id}`, `/console-defs`, `/system-defs`, `/console-folder-names`, `/standalones/{console_key}`; save/state history + rollback (issue #7): `GET /games/{slug}/save/history` + `POST /games/{slug}/save/restore` (and the `/state/` equivalents), with `save/meta`/`state/meta` now also reporting `size`; `_auth` auto-registers devices on first request; `GET /devices` includes `is_online`; `init()` accepts optional `data_dir` for ROM staging; `_device_event_queues` maps device IDs to asyncio queues for SSE delivery |
| `server/store/` | SQLite via stdlib `sqlite3`, split into a package: `__init__.py` composes `Store` from one mixin per table-group and re-exports the public surface (`Store`, `LOCK_TTL_HOURS`, `upsert_console_for_game`, dataclasses); `connection.py` = `_ThreadLocalConnection` (one SQLite connection per thread); `schema.py` = `_SCHEMA`/`_SCHEMA_VERSION`/`_migrate`; `models.py` = row dataclasses; `_base.py` = `StoreBase` (connection + schema/migration setup); `devices.py`/`games.py`/`blobs.py`/`locks.py`/`events.py`/`transfers.py`/`consoles.py`/`console_defs.py` = the per-domain CRUD mixins. Tables: `devices`, `consoles`, `games`, `game_devices`, `saves`, `states`, `locks`, `events`, `rom_transfers`, `rom_pull_requests`, `console_defs`, `system_defs`, `core_defs`, `console_folder_names`, `standalone_emulators`; schema version 7 (v7 adds `rom_transfers.sha256` for transfer integrity, issue #214; v6 added `console_key` to `core_defs`); `blobs.py` (`SaveStateMixin`) now **keeps history**: `_push_blob` appends a new generation instead of overwriting (deduping identical consecutive content) and prunes to the newest `HISTORY_LIMIT` (20) per game; the *current* blob is the most recently inserted row (ordered by `rowid` DESC, monotonic for inserts); `list_save_history`/`restore_save` (+ `state` equivalents) back the rollback feature, and `restore` re-inserts a past version's bytes as a new generation so history only grows forward; `ensure_device()` returns `(device, is_new)` tuple to signal first-time registrations; `rom_transfers` tracks pending ROM file deliveries (with a `sha256` of the staged file); `rom_pull_requests` tracks pending pull requests (receiver asks source to send); `console_defs`/`system_defs`/`core_defs`/etc. store global emulator/console definitions seeded by `cli/server.py` on startup (data from `cli/consoles_data.py`); `upsert_console_for_game(store, device_id, console_name, rom_path, save_path, rom_folder_path)` is a module-level helper (called by both `api.py` and `cli/game.py`) that infers emulator/folder paths from game paths and creates-or-updates the `Console` row |
| `server/config.py` | TOML config dataclass; load/save `~/.emusync/emusync.toml` |
| `server/mdns.py` | mDNS advertise + LAN discovery via `zeroconf` |
| `server/sync_client.py` | HTTP client wrapping all server endpoints (used by `emusync run`, `push`, `pull`); uses a persistent `httpx.Client` for connection pooling (keep-alive); sends PIN + device headers for auth; `GameDeviceConfig` holds `rom_path`, `save_path`, `launch_command`, `state_path`, `rom_folder_path`; `list_my_game_devices()`, `list_device_games()`, `get_device_consoles()`, `create_rom_transfer()`, `create_pull_request()`, `list_pending_pull_requests()`, `complete_pull_request()` support the push/pull flow; `download_transfer()` verifies the download against the server's `X-Rom-Hash`/recorded SHA256 and raises (deleting the partial file) on mismatch (issue #214); `list_save_history()`/`restore_save()` (+ `state` equivalents) back the history/rollback feature |
| `gui/electron/` (main process) | Split into per-domain modules (issue #222) — `main.ts` is now just IPC registration + app lifecycle (calls each module's `register*Ipc()`). Shared mutable state (server/game/daemon process handles, the window, console-def caches) lives on the single `rt` object in `runtime.ts` (ES modules only export read-only bindings, so cross-module reassignment needs an object). Modules: `runtime.ts` (constants `CONFIG_PATH`/`SCRIPT`/`PYTHON` + `rt`); `http.ts` (`httpGetJSON` — main process must use Node http, not `fetch`); `window.ts` (`createWindow`); `config-store.ts` (`config:*` IPC + `loadServerCfg`); `server.ts` (server + sync-daemon lifecycle, `server:*`/`daemon:*` IPC, `startServerProcess`/`killServerByPid`/`killOrphanServers`); `game.ts` (`game:*` IPC + `launcher:path`); `files.ts` (dialogs, `files:*`, `device:probe`, `findLatestFileInDir`); `sync.ts` (`save:*`/`state:*`/`rom:push` IPC); `emulator/{types,console-defs,detect,scan,ipc}.ts` (the import-wizard subsystem — `emulator:consoles`/`detect`/`scan` lazily fetch console defs from the Python API). Shared emulator types (`DetectedEmulatorOption`, `EmulatorScanResult`, `RomEntry`) live in `emulator/types.ts` and are type-imported by `preload.ts` |
| `gui/electron/preload.ts` | `contextBridge` — everything in `window.emusync.*` is defined here |
| `gui/renderer/src/api.ts` | Fetch wrapper for the Python REST API; holds `_base` URL + `_token` |
| `gui/renderer/src/time.tsx` | Timestamp formatting (issue #216): `formatRelative()` + the `<RelTime>` component render a relative phrase ("2 hours ago") with the exact local 12-hour time in a hover tooltip. **All EmuSync timestamps are UTC** (server `isoformat()`, Electron `toISOString()`), and a tz-less ISO string parses as *local* in JS — so `parseUtc()` appends `Z` when no offset/`Z` is present. Used by GameList, SaveHistory, DevicesButton, ServerStatusButton, GameConfig |
| `gui/renderer/src/App.tsx` | Root component; screen router; auto-starts server if `is_server=true` |
| `gui/renderer/src/components/Setup.tsx` | First-launch onboarding (choose server or join) |
| `gui/renderer/src/components/ServerStatusButton.tsx` | Server control panel modal (start/stop, PIN, LAN discovery, re-pair) |
| `gui/renderer/src/components/DevicesButton.tsx` | Paired devices list modal (shows count, last sync times, delete button per device) |
| `gui/renderer/src/components/GameList.tsx` | Main game list; play/edit/remove actions; bulk delete with checkboxes; per-game 🕘 button opens `SaveHistory` |
| `gui/renderer/src/components/SaveHistory.tsx` | Per-game save history + rollback modal (issue #7) — lists retained versions (time/size/source device), Restore makes a version current on the server and (if the game is local) writes it to disk via `save:pull` |
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

window.emusync.server.start()     // spawns emusync.py server start → { ok: boolean }
window.emusync.server.stop()      // SIGKILL server + pkill orphans + clean pid file
window.emusync.server.token()     // deprecated; returns null (no per-device tokens)
window.emusync.server.changePin(pin) // stops server, saves PIN to config, restarts
window.emusync.server.discover()  // runs emusync.py server discover-json → server list
window.emusync.server.localIp()   // returns this machine's LAN IPv4 address (os.networkInterfaces); null if none found

window.emusync.dialog.openFile()  // native file picker
window.emusync.dialog.openFolder() // native folder picker

window.emusync.emulator.consoles()          // returns ordered console list { key, label }[] for the dropdown
window.emusync.emulator.detect(consoleKey)  // scans for installed emulators for that console; checks RetroArch (native+flatpak) cores + standalone emulators (mGBA etc.); looks for console-specific ROM subfolders (GBA, SNES, NES, etc.) within the configured ROM directory; resolves per-core save subfolder; returns { options: DetectedEmulatorOption[], suggestions[] }
window.emusync.emulator.scan(consoleKey, emulatorOption, extraPaths[])  // scans only that console's ROM extensions; uses emulatorOption.saveDir (already resolved to core subfolder); returns { emulators, romDirs, roms[] } with consoleName+coreName on each entry
window.emusync.files.ensureSave(path)       // creates an empty save file + parent dirs if the file doesn't exist; called during import for games with no existing save
window.emusync.files.getSaveTime(path)      // returns last modified time of save file as ISO string (YYYY-MM-DDTHH:MM:SS), or null if file doesn't exist
window.emusync.files.getLatestInFolder(dir) // returns {path, time} for the newest file in dir, or null if dir is empty/missing
window.emusync.files.moveToSubfolder({romPath, subfolderName, newSavePath, newStateFolder}) // moves ROM into subfolderName/, migrates existing save from legacy locations to newSavePath, creates newStateFolder and migrates any legacy state files; returns {ok, newRomPath, newSavePath, newStateFolder, error?}

window.emusync.save.push(slug, savePath)   // reads local save file, POSTs bytes to /games/{slug}/save; returns {ok, error?}
window.emusync.save.pull(slug, savePath)   // GETs /games/{slug}/save, backs up existing file to .bak, writes new bytes; returns {ok, pulled, error?}

window.emusync.state.push(slug, stateFolder) // tar.gz all files in stateFolder, POSTs archive to /games/{slug}/state; returns {ok, error?}
window.emusync.state.pull(slug, stateFolder) // GETs /games/{slug}/state archive, backs up existing files to .bak (RETAINED on success — one generation, so an overwrite stays recoverable), extracts all files into stateFolder; restores backups on failure; returns {ok, pulled, error?}

window.emusync.device.probe(ip, port)      // TCP probe: resolves true if ip:port reachable within 2 s

window.emusync.launcher.path()             // absolute path to emusync launcher binary

window.emusync.game.launch(slug)           // spawns `emusync run <slug>` (emulator command derived server-side from the game config)
window.emusync.game.stop()                 // SIGKILL game process group (in-app launches)
window.emusync.game.stopExternal()         // kill emulator + emusync via .game_pid file (Steam launches)
window.emusync.game.hasPidFile()           // true if .game_pid exists, process is alive, and cmdline contains emusync/python
window.emusync.game.isRunning()            // boolean
window.emusync.game.onExited(cb)           // subscribe to game:exited event
window.emusync.game.offExited(cb)          // unsubscribe

window.emusync.daemon.start()              // spawn emusync sync-daemon (client devices only; no-op on server or if already running)
window.emusync.daemon.stop()               // kill the sync daemon if running
```

When adding a new IPC channel, add the handler to `main.ts` AND the bridge entry to `preload.ts`. The renderer's TypeScript sees `window.emusync` as `any` (no separate `.d.ts`) — the global type declaration lives in `Setup.tsx`.

---

## Config and data paths

| Path | Contents |
|------|----------|
| `~/.emusync/emusync.toml` | Per-device config (server host, port, PIN, device ID/name, is_server flag, recent ROM folders) |
| `~/.emusync/emusync.db` | SQLite database (devices, games, saves, locks) |
| `~/.emusync/.server_pid` | PID of the running server process (written on start, deleted on clean exit) |
| `~/.emusync/.game_pid` | Two-line file: line 1 = emusync run PID, line 2 = emulator child PID (written by `emusync run`, deleted on exit) |
| `~/.emusync/rom_staging/` | Staged ROM files for pending transfers (named `{transfer_id}{ext}`); created by `POST /games/{slug}/rom-transfer` |
| `~/.emusync/game_cache/{slug}.json` | Cached per-device game config (rom/save/state/launch paths), written by `emusync run` on each online launch so an offline launch knows the paths |
| `~/.emusync/offline_plays.json` | Append-only log of offline plays (`slug`, `started_at`, `ended_at`, save mtime/hash) for save-conflict resolution (issue #5) |
| `~/.emusync/save_conflicts.json` | Append-only log of auto-resolved save divergences (`slug`, `resolved_at`, `winner`, local/server hashes) written by `emusync run` when both copies changed (issue #5) |

Config fields: `server_host`, `server_port`, `data_dir`, `device_id`, `device_name`, `is_server`, `server_pin` (optional — blank = open access), `recent_import_folders` (dict mapping console keys to lists of recent folder paths).

---

## Server process lifecycle

- **Initialization:** When `emusync server start` is run on a fresh device (`is_server=false`), the user is prompted to initialize the server interactively. This sets a PIN and confirms the port before startup.
- **Duplicate-launch detection:** `emusync server start` checks if a server is already running by reading `.server_pid` and verifying the process exists. If running, it exits gracefully with a message showing the PID and port. Stale PID files are cleaned up automatically.
- **Start:** `startServerProcess()` in `main.ts` spawns Python with `PYTHONUNBUFFERED=1`; waits for server startup signal in stdout; returns `{ ok: boolean }`. Renderer health-polls to confirm server is ready.
- **Stop:** Can be triggered from GUI ("Stop Server" button) or CLI (`emusync server stop`). GUI method: SIGKILL `serverProcess` + read `.server_pid` and SIGKILL that PID + `pkill -9 -f "emusync.py server start"`. CLI method: checks `.server_pid`, kills that process, echoes "server not running" if not active. All methods clean up the PID file. Resets `serverStartedByApp` flag in GUI.
- **Restart:** Available as `emusync server restart` CLI command. Calls `_do_stop_server()` to stop the running server (or echoes "server not running"), then calls `_do_start_server()` to start it again. Useful for applying configuration changes.
- **App close:** `window-all-closed` only kills the server if the GUI spawned it (`serverStartedByApp=true`). This flag is set only when `startServerProcess()` detects the "Pairing token:" message in stdout, not when the Python process exits due to duplicate-launch detection. This allows users to start a server externally (e.g., via terminal) and close the GUI without killing it.
- **Auto-start:** `App.tsx` calls `server.start()` on init if `is_server=true` in config. If a server is already running (external start), the Python code exits gracefully with duplicate-launch detection, and the GUI does not manage its lifecycle.

---

## Server activity logging (terminal output)

The server prints real-time activity to stdout for operator visibility. **Every line is timestamped** with a `[YYYY-MM-DD HH:MM:SS] ` prefix:

```
[2026-06-09 14:03:18] EmuSync server ready
[2026-06-09 14:03:18] EmuSync server running on :8765
[2026-06-09 14:03:21] new device paired called steamdeck at ip:192.168.1.42
[2026-06-09 14:05:02] steamdeck online
[2026-06-09 14:10:44] Pokemon Emerald is running on steamdeck
[2026-06-09 14:10:45] save pulled: Pokemon Emerald by steamdeck
[2026-06-09 14:55:12] save pushed: Pokemon Emerald from steamdeck
[2026-06-09 14:55:13] Pokemon Emerald stopped on steamdeck
[2026-06-09 15:01:00] steamdeck went offline
[2026-06-09 15:30:00] steamdeck unpaired
```

**Timestamping** — `cli/server.py` defines `_TimestampedStream` (a thin `sys.stdout` wrapper) and installs it via `_install_timestamped_stdout()` at the top of `_do_start_server`. It prefixes every newly started line (thread-safe, `\r`-aware), so all current *and* future stdout lines — `click.echo`, `print`, `api._print_activity`, the transfer-daemon log — are timestamped uniformly without touching each call site. It does **not** wrap stderr (e.g. the mDNS warning) or uvicorn's own logs.

**The full set of server stdout lines:**

| Line | Where | When |
|------|-------|------|
| `EmuSync server ready` / `EmuSync server running on :<port>` | `cli/server.py` | startup (the GUI's `main.ts` matches `EmuSync server ready` via `.includes()` to confirm it started — keep that substring intact) |
| `EmuSync server is already running …`, `Server (PID …) stopped.`, `server not running`, init/clear-devices messages | `cli/server.py` | lifecycle commands |
| `new device paired called <name> at ip:<ip>` | `api._auth()` | first INSERT for a device (`ensure_device` returns `is_new=True`) |
| `<name> online` | `api._auth()` | a known device requests while not in `_online_devices` |
| `<name> went offline` | `_monitor_presence()` daemon thread | device idle > 5 min (checked every 30 s) |
| `<name> unpaired` | `DELETE /devices/{id}` | device removed (printed before deletion) |
| `<game> is running on <device>` | `POST /games/{slug}/lock` | lock acquired (game launched) |
| `<game> stopped on <device>` | `DELETE /games/{slug}/lock` | lock released (the stop time is the timestamp prefix) |
| `save pushed: <game> from <device>` / `save pulled: <game> by <device>` | `POST` / `GET /games/{slug}/save` | save sync (pull only logs when a save actually exists, i.e. not a 204) |
| `state pushed: <game> from <device>` / `state pulled: <game> by <device>` | `POST` / `GET /games/{slug}/state` | state sync (pull only logs on a real hit) |
| `ROM pushed: <game> from <device> → <target> (queued)` | `POST /games/{slug}/rom-transfer` | ROM staged for delivery |
| `ROM pulled: <game> by <device>` | `GET /rom-transfers/{id}/file` | target device downloads the staged ROM |

`api._print_activity(msg)` is the single sink for the API-side lines — it does one atomic `sys.stdout.write(msg + "\n")` (so concurrent worker threads can't interleave). `_game_label(slug)` / `_device_label(device_id)` resolve human-readable names (device names come from the `_device_names` cache `_auth` populates, falling back to a `list_devices` scan, then the raw id).

**Thread safety:** The `_online_devices` set and `_device_names` dict are protected by `_presence_lock` (threading.Lock) because FastAPI's synchronous dependencies like `_auth` may run in concurrent worker threads. `_TimestampedStream` has its own lock so writes from those same threads stay line-atomic.

---

## Authentication (PIN-only model)

- **Server PIN:** Set in `server_pin` config field. All clients send `Authorization: Bearer {PIN}` on API requests.
- **Device registration:** Devices auto-register on first authenticated request using `X-Device-ID` and `X-Device-Name` headers. No explicit pair/token step.
- **Blank PIN:** If `server_pin` is empty, any request is allowed (open access — useful on trusted LANs).
- **Changing the PIN:** `server:change-pin` IPC saves new PIN to config and restarts the server. Existing device records persist; they just need the new PIN for reconnection.
- **Client connection:** On first launch, user enters server host/port/PIN. Renderer calls `configure(host, port, pin)` and `configureDevice(deviceId, deviceName)` (or these are auto-loaded from config). All subsequent API calls include PIN + device headers.

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
- You added a new `Store` method (in the relevant `server/store/` mixin) → test it directly via `Store(tmpdir)` or through the API
- You added a CLI subcommand (in the `cli/` package — add it to the relevant command-group module) → note it in the PR; CLI-level tests are optional but preferred for logic-heavy commands
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

For multi-device tests or tests needing custom PINs:

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

For tests that need blank-PIN (open access) or direct store access:

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

Look for any `feature/*` or `copilot/*` branch that is likely to touch the same files. If one exists, stop and flag it to the user before writing any code — two branches editing `api.py` or `server/store/` simultaneously will produce a painful merge.

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
- **API**: new `/games/{slug}/state` routes (GET/POST) and `/games/{slug}/state/meta`
- **CLI (`emusync run`)**: pulls state before launch, pushes after exit (opt-in if `state_path` is configured); auto-detects actual save/state file extensions and updates config if needed
- **Electron**: detects `savestate_directory` from `retroarch.cfg`, scans for `.state` / `.state.auto` files per ROM
- **GUI**: wizard shows `✓ State found` / `⊕ State will be created` badges; does not pre-create files, only tracks paths

State sync is **opt-in** — if a game's `state_path` is empty, it is skipped silently. The scan handler checks both the per-core subfolder and the root `states/` dir for backwards compatibility with pre-existing states.

**Auto-detection of the real save/state path (extension *and* folder)** — During import, games are registered with a default save/state path derived from the ROM filename (e.g. `saves/SNES/game.sav`), but RetroArch names files after the **content name**, which differs by launch method: the ROM filename when loaded by path, or the **database/playlist label** when loaded from a scanned playlist (e.g. `states/Pokémon Pinball_ Ruby & Sapphire [2003]/` — note `:`→`_` and the `[year]`). So the real save/state can sit under a different extension *and/or* a different folder. After the emulator exits, `emusync run` records a pre-launch timestamp and detects which save/state was actually written **this session** (`_resolve_written_save` / `_resolve_written_state` in `cli/run.py`): if the configured location was the one written, it's kept; otherwise the wrapper adopts the newest save file / state folder written under the saves/states root (`.bak` files excluded) and updates the `game_device` config (preserving `rom_folder_path`). The policy is conservative — a working config is never switched away from. **Limitation:** EmuSync only sees what RetroArch wrote during an EmuSync-wrapped launch; a save made in a pure RetroArch-direct session is only picked up once a wrapped launch writes to the same folder (issue #210).

---

## ROM Folder Tracking

During console import, the `rom_folder_path` is extracted from each ROM file path and saved with the game config. This allows:
- Future features to re-scan specific folders for game updates
- Tracking which folder contained each game's ROM file
- Managing multiple games from the same directory

The path is extracted from the full ROM file path during import and returned by `GET /games/{slug}/device` endpoint alongside `rom_path`, `save_path`, `state_path`, and `launch_command`.

---

## ROM Transfer (`emusync push` / `emusync pull`)

### `emusync push` — send a ROM to another device

`emusync push` is an interactive wizard that transfers ROM files from the current device to another via the central server:

**Flow:**
1. Lists all games on this device that have a `rom_path` configured
2. User multi-selects games (e.g. `1`, `1,3`, `1-4`)
3. Lists other paired devices with online/offline status
4. User selects target device
5. For each game: checks if the target device has the console configured (via `consoles` table or `game_devices`); if found, proposes the known ROM folder; user confirms or enters a custom path
6. Streams each ROM to the server staging area via `POST /games/{slug}/rom-transfer`
7. Server creates a `rom_transfers` record (status=pending); responds with `target_online` bool
8. CLI shows "queued — device is online" or "⚠ offline — will be delivered when it comes online"

### `emusync pull` — request a ROM from another device

`emusync pull` is the reverse of push: the current device requests a ROM from a source device. The source's sync-daemon fulfills the request by uploading the ROM via the server.

**Flow:**
1. Lists other paired devices with online/offline status
2. User selects the source device
3. Lists games on the source device that have a `rom_path` (via `GET /devices/{id}/game-devices`)
4. User multi-selects games to pull
5. For each game: checks if this device has the console configured locally; if found, proposes the local ROM folder; user confirms or enters a custom path
6. Sends `POST /games/{slug}/rom-pull-request` with `from_device_id` and `destination_path`
7. Server creates a `rom_pull_requests` record and SSE-notifies the source device
8. CLI shows "request sent — source is online" or "⚠ offline — ROM will be sent when it comes online"
9. Source device's sync-daemon handles `rom_pull_requested` event: looks up local ROM path, calls `create_rom_transfer`, marks request fulfilled
10. Requester's sync-daemon receives the resulting `rom_transfer_queued` event and downloads normally

**API surface:**
- `POST /games/{slug}/rom-transfer` — streams ROM bytes (body) with `X-To-Device-ID`, `X-Destination-Path`, `X-Filename` headers; stages file to `~/.emusync/rom_staging/{transfer_id}/{filename}`, hashing the stream (SHA256) into `rom_transfers.sha256`; returns `{transfer_id, status, target_online}`. The hash is surfaced to the receiver in the pending-transfer list, the `rom_transfer_queued` SSE event, and the `X-Rom-Hash` download header, so `download_transfer` can verify integrity and reject a corrupt transfer (issue #214)
- `GET /game-devices` — returns all games configured for the calling device (slug, name, console, rom_path, save_path, …)
- `GET /devices/{id}/game-devices` — returns all games configured for any specific device
- `GET /devices/{id}/consoles` — returns console configs (name, ROM folder, save folder, emulator) for any device
- `POST /games/{slug}/rom-pull-request` — creates a pull request; body `{from_device_id, destination_path}`; SSE-notifies source; returns `{pull_request_id, status, source_online}`
- `GET /rom-pull-requests/pending` — returns pending pull requests where calling device is the source (needs to fulfill)
- `PUT /rom-pull-requests/{id}` — mark pull request as `fulfilled` or `failed` (source device only)

**Staging dir:** `~/.emusync/rom_staging/{transfer_id}/{original_filename}` — subdirectory per transfer preserves the original filename with no modification. The per-transfer subdir is deleted once the receiver marks the transfer `completed`/`failed` (`_remove_staging_dir` in `api.py`), and `api.init()` runs `_sweep_stale_staging()` on startup to drop any subdir whose transfer is gone or no longer pending — so staged ROMs don't accumulate on disk (issue #202).

**Auto-delivery via `emusync sync-daemon`**: run this on any device to handle both sides automatically. On startup it drains pending transfers (incoming ROMs) and pending pull requests (ROMs this device needs to send). Then holds an SSE connection open. Handles two event types:
- `rom_transfer_queued` → downloads ROM, registers game in game list
- `rom_pull_requested` → looks up local ROM, uploads it via `create_rom_transfer`

Reconnects automatically on connection loss. Built into `emusync server start` as a background thread for server devices.

**`sync_client.py` delivery methods**: `list_pending_transfers()`, `download_transfer(id, dest)`, `complete_transfer(id)`, `list_pending_pull_requests()`, `complete_pull_request(id)`, `list_device_games(device_id)`, `create_pull_request(slug, from_device_id, destination_path)`, `stream_events()` (SSE generator).

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

**Orphaned server processes** — If Electron exits abnormally, the uvicorn server can keep running. The stop handler uses three kill strategies (see Server process lifecycle above). If you see "port already in use", run: `pkill -9 -f "emusync.py server start"`. Note: `emusync server start` now detects running servers and exits gracefully instead of attempting to start a duplicate.

**SIGKILL skips Python finally blocks** — `.server_pid` and `.server_token` files may not be cleaned up after a hard kill. The stop handler manually deletes them.

**WSL2 + Electron** — Requires `--no-sandbox` (baked into `npm run dev`). Needs `DISPLAY=:0` set. dbus errors in the output are harmless noise.

**Stale DB schema** — If you see `sqlite3.OperationalError: no such column`, delete `~/.emusync/emusync.db` and restart the server.

**TypeScript on `window.emusync`** — Typed as `any`; the global interface declaration is in `Setup.tsx`. If you add new IPC channels, add them there too or type errors won't surface at compile time.

**RetroArch config paths use `~` which Node.js does not expand** — `retroarch.cfg` commonly stores paths like `savefile_directory = "~/.config/retroarch/saves"`. `parseRetroArchCfg` in `main.ts` expands leading `~/` to the real home directory so that `existsSync`, `mkdirSync`, and `join` work correctly. Do not call `parseRetroArchCfg` without passing `home` and do not use raw config values as filesystem paths without checking for tilde. Also, `rgui_browser_directory = "default"` is RetroArch's placeholder for "not configured" — it is filtered out and never passed as a ROM directory.

**RetroArch per-core save directory is always `saves/<CoreName>/`** — `detectEmulatorsForConsole` uses `join(ra.saveDir, core.folderName)` unconditionally. The old `resolveCoreSaveDir` fell back to the root saves dir if the subfolder did not exist yet, causing saves to land in the wrong place on fresh installs. The scan handler additionally checks the root saves dir as a fallback when looking for *existing* saves written before per-core organisation was set up.

**RetroArch "Sort saves/states by content directory"** — The canonical path model is: saves at `savesRoot/GameName/GameName.srm` and states as a FOLDER at `statesRoot/GameName/` (all slots live there). `state_path` in `game_devices` stores the FOLDER path, not a single file. Both the GUI IPC handlers (`state:push` / `state:pull`) and `sync_client.py` (`push_state` / `pull_state`) detect whether `state_path` is a directory: if so, they pack/extract all files as a **tar.gz archive** so every state slot (`.state`, `.state1`, `.state.auto`, …) is synced. `emusync run` always pushes the whole folder after the game exits (no hash comparison for folders). **State pulls are non-destructive:** the folder extractor (`_extract_state_folder` in `sync_client.py`, and the `state:pull` handler) backs up every overwritten file to `.bak` and *retains* it (one generation, via `os.replace`/unlink-then-rename so it's Windows-safe) — the previous code deleted the backups on success, losing the overwritten state (issue #204). Correspondingly, `push_state` / `state:push` **exclude `.bak` files** so backups never propagate to the server or peers. `pull_state` falls back to writing raw bytes as `GameName.state` if the server blob is not a valid tar archive (legacy compatibility). The `emulator:scan` handler computes the target save/state paths using the content-dir pattern (`savesRoot/GameName/` and `statesRoot/GameName/`) and checks legacy core-subfolder and flat-root paths only as fallbacks for detecting already-existing files. The default registered path always uses the content-dir pattern even when the file/folder doesn't exist yet.

**`store.add_game` is INSERT OR IGNORE, not INSERT OR REPLACE** — `add_game` only inserts new rows; it never overwrites. Use `update_game_name(slug, name)` to rename an existing game. The original `INSERT OR REPLACE` bug cascade-deleted `game_devices`, `saves`, and `locks` every time a game was renamed, causing the game list to appear empty after a config save.

**Duplicate-launch guard in `emusync run`** — Before acquiring the lock, the wrapper checks the lock state. If the lock is already held (by this device or another), it calls `_show_game_running_popup` which displays "\<game\> is already running. Please close it on \<device\>." and then exits. The popup uses a subprocess fallback chain — `notify-send` → `zenity` → `kdialog` → `xmessage` → tkinter — so it works on Wayland, X11, Steam Deck Gaming Mode (gamescope), and environments where `libtk` may not be installed. `notify-send` fires first and is non-blocking (auto-dismisses); the chain then continues to the first available blocking dialog so desktop users still get a modal. The race-condition path (409 from `acquire_lock`) follows the same flow.

**DB thread safety — one connection per thread, not a shared one** — `server/store/connection.py` provides `_ThreadLocalConnection`, which lazily creates a separate `sqlite3.Connection` per thread (cached in `threading.local`) and dispatches `execute`/`commit`/attribute access to it. The store is hit from many threads (uvicorn's worker-thread pool *and* the `_monitor_presence` daemon thread), and a single shared connection cannot be used safely for concurrent cursor access: one thread's `execute`/`commit` landing between another thread's `execute()` and its `fetchone()`/`fetchall()` corrupts the in-flight statement and raises `sqlite3.InterfaceError: bad parameter or other API misuse`, after which the connection is wedged (issue #200). With WAL (enabled per connection) this gives concurrent readers plus a single writer; the 30 s busy timeout handles writer contention. **`PRAGMA foreign_keys` is per-connection**, so it is set on every connection in the factory — do not assume FKs are on for a connection without setting them. Each connection uses `check_same_thread=False`. Schema initialization (in `server/store/_base.py`) runs on fresh databases only, with each statement executed individually because `executescript()` is deprecated and incompatible with WAL mode. Do not reintroduce a single shared connection guarded by a lock that releases before fetch — that is exactly the bug that was removed.

**DB schema versioning — use `PRAGMA user_version`, not try/except** — `server/store/schema.py` tracks the schema version in `PRAGMA user_version` (currently `_SCHEMA_VERSION = 6`). When adding a new migration: (1) add a new `if from_version < N:` block in `_migrate()`, (2) bump `_SCHEMA_VERSION` to N, (3) add the new table/column definitions to `_SCHEMA` so fresh DBs get them without running migrations. Do not add bare `try/except ALTER TABLE` blocks outside `_migrate()` — warm-start DBs skip `_migrate()` entirely via the version check. **Fresh DBs are stamped with `PRAGMA user_version = _SCHEMA_VERSION` in `server/store/_base.py` right after `_SCHEMA` is applied**, so they skip `_migrate()` too — do not remove that stamp, or every new install re-runs the whole migration chain against the schema it just created (issue #202).

**`config:load` returns `null` when config is absent** — `main.ts` IPC handler `config:load` returns `null` both when the TOML file doesn't exist and when it fails to parse. Callers should check for `null` rather than calling the separate `config:exists` IPC first (which is kept for backwards compatibility but is now redundant).

**mDNS runs in a background thread** — In `emusync.py server start`, mDNS advertisement runs in a `daemon=True` thread so the pairing token is printed (and Electron can resolve) without waiting for mDNS socket/network probing. The server's `finally` block joins the thread (2 s timeout) before unregistering the service.

**Token is printed before uvicorn binds** — `emusync.py server start` prints `Pairing token:` before calling `uvicorn.run()`. Any code that calls `server.start()` and then immediately calls the API will get connection refused. Always poll `/health` after `server.start()` resolves before making any API calls (including `/pair`). Both `App.tsx` and `Setup.tsx` do this.

**Blank PIN servers must match in the token regex** — `startServerProcess` in `main.ts` looks for `Pairing token: (\S*)` (zero-or-more, not `\S+`). `server_pin` defaults to `""`, so the printed line is `"Pairing token: "` with no value. Using `\S+` would never match and fall through to the 5-second timeout.

**Electron main process must use http.get, not fetch** — The Electron main process is Node.js, not a browser. The browser `fetch()` API doesn't work correctly in that context. Use Node.js `http.get()` (from the `http` module) with a helper wrapper that returns `Promise<{ status, body?, error? }>`. The renderer process can use normal `fetch()` — only the main process (`main.ts`) is affected.

**`server_host` is empty string on server devices** — Server devices store `server_host = ""` in `emusync.toml` because they connect to themselves. Any code in `main.ts` that reads `cfg.server_host` must fall back to `"localhost"` when the value is empty: `const host = (cfg.server_host as string) || "localhost"`. Never use `!cfg.server_host` as a "not configured" guard — check `!cfg.server_port` instead.

---

## Keeping this file updated

Update this file when any of the following change:

- CLI subcommands added or removed (the `cli/` package)
- IPC channels added or removed (`main.ts` / `preload.ts`)
- New React components added to `gui/renderer/src/components/`
- Config fields added or removed (`server/config.py`)
- New data files written to `~/.emusync/`
- Python or Node dependency changes (`requirements.txt`, `package.json`)
- Release or CI/CD process changes
- Changes to `install.sh`, `Makefile`, or `emusync-server.service`

A pre-commit hook (`.git/hooks/pre-commit`) warns when architecture files change without this file being updated. Run `bash install.sh` to install it.
