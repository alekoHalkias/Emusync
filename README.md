# EmuSync

LAN save-file sync for emulators. Keeps game saves in sync across devices (gaming PC ↔ Steam Deck) on a home network — no cloud, no accounts, no port forwarding.

---

## How it works

One machine runs the **server** (your gaming PC). Other devices **pair** with it over mDNS — no IP config needed. The `emusync run` wrapper pulls the latest save before launch and pushes it back after you quit. Locks prevent two devices from playing the same game at the same time.

The GUI (Electron + React) can also launch games directly — it spawns `emusync run` in the background, which handles save sync automatically.

---

## Project layout

```
emusync.py              ← CLI entry point (all commands live here)
emusync                 ← generated shell launcher (created by install.sh)
install.sh              ← one-shot setup script
Makefile                ← dev shortcuts
requirements.txt        ← Python deps
pyproject.toml          ← package metadata

tests/
└── test_integration.py ← integration tests (real SQLite, no mocks)

.github/workflows/
├── ci.yml              ← runs tests on push/PR to Aleko-andrewVersion and main
└── release.yml         ← builds AppImage + publishes GitHub Release on version tags

server/
├── api.py              ← FastAPI REST API (all endpoints)
├── config.py           ← TOML config (~/.emusync/emusync.toml)
├── store.py            ← SQLite database (devices, games, saves, locks)
├── mdns.py             ← mDNS advertise + LAN discovery (zeroconf)
└── sync_client.py      ← HTTP client wrapping all server endpoints

gui/
├── electron/
│   ├── main.ts         ← Electron main process: IPC handlers, spawns Python
│   └── preload.ts      ← contextBridge API exposed to renderer
├── renderer/
│   ├── index.html
│   └── src/
│       ├── App.tsx             ← root component, screen router, game running state
│       ├── api.ts              ← fetch wrapper for the Python REST API
│       ├── index.tsx           ← React entry point
│       ├── styles.css
│       └── components/
│           ├── Setup.tsx       ← first-launch onboarding (server or join)
│           ├── GameList.tsx    ← main game list with play/edit/remove
│           ├── GameConfig.tsx  ← add/edit game form with file pickers
│           └── StatusBadge.tsx ← live server health indicator
├── electron.vite.config.ts
└── package.json
```

---

## Setup

**Requirements:** Python 3.10+, Node 18+, npm

```bash
git clone https://github.com/alekoHalkias/Emusync
cd Emusync
bash install.sh
```

`install.sh` creates `.venv/`, installs Python deps, installs Node deps in `gui/`, and writes an `emusync` launcher script.

---

## Running

### Backend (required before GUI)

```bash
# On the server machine — prints the pairing token on first run
.venv/bin/python emusync.py server start
# or:
make dev-server
```

### GUI (development)

```bash
# In a separate terminal:
cd gui && npm run dev
```

On **WSL2** the display needs to be exported and `--no-sandbox` is required (already baked into the dev script):

```bash
DISPLAY=:0 WAYLAND_DISPLAY=wayland-0 npm run dev --prefix gui
```

### GUI (production build / AppImage)

```bash
cd gui
npm run dist       # builds AppImage under gui/dist/
# Move the AppImage out of the repo before running to avoid committing it:
mv gui/dist/*.AppImage ~/
~/EmuSync.AppImage --no-sandbox
```

---

## First-time game setup (GUI)

1. **Server must be running** (`make dev-server` in one terminal)
2. Open the GUI — it reads `~/.emusync/emusync.toml` for the server address + token
3. Click **Add Game** and fill in:
   - **Name** — display name, e.g. `Pokemon Emerald`
   - **ROM Path** — full path to the ROM file
   - **Save Path** — full path RetroArch writes its save to (`.srm`, not `.sav`)
   - **Launch Command** — full emulator command, e.g.:
     ```
     retroarch -L /usr/lib/x86_64-linux-gnu/libretro/mgba_libretro.so "/path/to/rom.gba"
     ```
4. Click **Play** → **Launch now** to pull the save and launch the emulator

> **RetroArch note:** libretro cores on Ubuntu/Debian are at  
> `/usr/lib/x86_64-linux-gnu/libretro/<core>_libretro.so`  
> RetroArch saves GBA games as `.srm` (not `.sav`) — use that as the Save Path.

---

## CLI reference

```bash
.venv/bin/python emusync.py server start

.venv/bin/python emusync.py device pair [--host <ip>] [--port <port>] --token <token>
.venv/bin/python emusync.py device list

.venv/bin/python emusync.py game add [<slug>] --name "Game Name" [--rom <path>] [--save <path>] [--command <cmd>]
.venv/bin/python emusync.py game list
.venv/bin/python emusync.py game edit <slug> [--name] [--rom] [--save] [--command]
.venv/bin/python emusync.py game remove <slug>

.venv/bin/python emusync.py sync status

# Steam launch wrapper — paste into Steam → game properties → launch options:
emusync run --game <slug> -- %command%
```

---

## REST API

Server runs on port `8765`. Auth header: `Authorization: Bearer <token>`.

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/health` | no | Health check |
| POST | `/pair` | no | Pair a device (requires master token) |
| GET | `/devices` | yes | List paired devices |
| GET/POST | `/games` | yes | List / add games |
| GET/PUT/DELETE | `/games/:slug` | yes | Get / update / remove a game |
| GET/PUT | `/games/:slug/device` | yes | Per-device ROM path, save path, launch command |
| GET/POST | `/games/:slug/save` | yes | Pull / push save blob |
| GET | `/games/:slug/save/meta` | yes | Save hash + timestamp |
| POST/DELETE/GET | `/games/:slug/lock` | yes | Acquire / release / check lock |

---

## Config file

Location: `~/.emusync/emusync.toml`

```toml
server_host = "192.168.1.50"   # empty on the server machine
server_port = 8765
data_dir    = "/home/user/.emusync"
device_id   = "<uuid>"
device_name = "my-pc"
token       = "<bearer-token>"
is_server   = false
```

Set `EMUSYNC_CONFIG_DIR` to override the config directory — used to simulate two devices on one machine during testing.

---

## CI/CD

**On every push to any branch, and on PRs into `main`:**
GitHub Actions runs the full test suite. The commit gets a green check or red X.

**To publish a release:**
```bash
make release VERSION=v1.0.0
```
This tags the commit and pushes the tag. GitHub Actions then:
1. Runs all tests — fails fast if anything is broken
2. Builds the AppImage on Ubuntu
3. Creates a GitHub Release at `github.com/alekoHalkias/Emusync/releases` with the AppImage attached and auto-generated release notes from commit messages

AppImages are only built on version tags — not on every push to main. You control exactly when a release goes out.

---

## Makefile shortcuts

```bash
make install                  # run install.sh
make dev-server               # start Python backend via venv
make dev-gui                  # cd gui && npm run dev
make build-gui                # cd gui && npm run build
make lint                     # syntax-check Python files
make test                     # run integration tests
make release VERSION=v1.0.0   # tag + push to trigger a release build
```

---

## IPC surface (Electron ↔ renderer)

Defined in `gui/electron/preload.ts`, consumed via `window.emusync.*`:

```typescript
window.emusync.config.load()         // → EmusyncConfig | null
window.emusync.config.save(data)     // → boolean
window.emusync.config.exists()       // → boolean

window.emusync.server.start()        // → { ok, token }
window.emusync.server.stop()         // → boolean

window.emusync.dialog.openFile()     // → string | null

window.emusync.game.launch(slug, command)  // spawns emusync run → { ok }
window.emusync.game.stop()                 // kills running game process group → { ok }
window.emusync.game.isRunning()            // → boolean
window.emusync.game.onExited(cb)           // subscribe to game exit event
window.emusync.game.offExited(cb)          // unsubscribe
```

`game.launch` spawns `emusync run --game <slug> -- <command>` using the `.venv` Python. It tracks the process and sends a `game:exited` IPC event to the renderer when it ends. `game.stop` kills the entire process group (so the emulator subprocess is also killed) and the Python SIGTERM handler ensures the lock is released.

---

## Known gotchas

**Stale DB schema** — if you see `sqlite3.OperationalError: no such column`, the DB schema changed since the DB was created. Fix: `rm ~/.emusync/emusync.db` and restart the server. Re-add games and re-push saves.

**Lock stuck after hard kill** — if a game process is killed with SIGKILL (not SIGTERM), the lock won't release automatically. Fix: `DELETE /games/<slug>/lock` via API or restart the server.

**WSL2 `--no-sandbox`** — Electron requires `--no-sandbox` in WSL2. Already baked into `npm run dev`. For production builds, pass it on the command line.

**Electron uses `.venv` Python** — `main.ts` auto-detects `.venv/bin/python` next to `emusync.py`. Set `EMUSYNC_PYTHON` env var to override if your venv is elsewhere.

**AppImage + FUSE on WSL2** — AppImages need `libfuse2`: `sudo apt-get install libfuse2`.

---

## Key design decisions

- **No cloud.** mDNS only — devices find each other like a printer on your LAN.
- **Lock stale after 4 hours** — a crashed session never blocks the other device forever.
- **Save backup on pull** — existing save copied to `.bak` before overwrite.
- **`emusync run` always releases the lock** even if the emulator crashes (`try/finally` + SIGTERM handler).
- **Remove game = remove from management only.** Files on disk are never deleted.
- **GUI and CLI are equivalent.** Everything in the GUI is also a CLI command.
- **Electron reads config directly** via `smol-toml` — no round-trip to the Python server needed for setup.
