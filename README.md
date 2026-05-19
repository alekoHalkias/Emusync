# EmuSync

LAN save-file sync for emulators. Keeps game saves in sync across devices (gaming PC ↔ Steam Deck) on a home network — no cloud, no accounts, no port forwarding.

## How it works

- One machine runs the **server** (the gaming PC)
- Other devices **pair** with it over LAN via mDNS discovery
- The `emusync run` wrapper syncs the save before and after each play session
- Locks prevent two devices from playing the same game simultaneously

## Stack

- **Backend:** Python (FastAPI REST API, SQLite, zeroconf mDNS, Click CLI)
- **GUI:** TypeScript + Electron
- **Config:** `~/.emusync/emusync.toml`

## Project layout

```
backend/
├── cli.py                  ← entry point for all CLI commands
└── emusync/
    ├── config.py           ← TOML config (~/.emusync/emusync.toml)
    ├── store.py            ← SQLite store (devices, games, saves, locks)
    ├── server.py           ← FastAPI REST API
    ├── mdns_service.py     ← mDNS advertise + LAN discovery
    └── sync_client.py      ← HTTP client wrapping all server endpoints

gui/
├── src/
│   ├── main.ts             ← Electron main process (spawns Python backend)
│   ├── preload.ts          ← IPC bridge to renderer
│   └── renderer/app.ts     ← Full UI (onboarding, game list, game config)
└── renderer/
    ├── index.html
    └── styles.css
```

## Setup (development)

**Requirements:** Python 3.10+, Node 18+, npm

```bash
# Install Python deps
cd backend
pip install -r requirements.txt

# Install GUI deps
cd ../gui
npm install
```

## Running

### CLI only

```bash
cd backend

# On the server machine (gaming PC):
python3 cli.py server start
# Prints a pairing token — keep it, you'll need it on the other device

# On the client machine (Steam Deck):
python3 cli.py device pair --host <server-ip> --token <pairing-token>
```

### GUI

```bash
cd gui
npm start            # Linux/WSL with display
npm start -- --no-sandbox   # WSL2 without WSLg
```

The GUI auto-starts the Python backend. On first launch it walks through server setup or device pairing.

## CLI reference

```bash
python3 cli.py server start

python3 cli.py device pair --host <ip> --token <token>
python3 cli.py device list

python3 cli.py game add <slug> --name "Game Name" --rom /path/to.rom --save /path/to.sav
python3 cli.py game list
python3 cli.py game edit <slug> --name --rom --save --command
python3 cli.py game remove <slug>

python3 cli.py sync status

# The Steam launch wrapper:
python3 cli.py run --game <slug> -- <emulator command>
# e.g.: python3 cli.py run --game zelda -- retroarch -L snes.so game.sfc
```

## REST API

Server runs on port `8765` by default.

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/health` | no | Health check |
| POST | `/pair` | no | Pair a device (requires master token) |
| GET | `/setup-state` | no | Config state (for GUI onboarding) |
| GET | `/devices` | yes | List paired devices |
| GET/POST | `/games` | yes | List / add games |
| GET/PUT/DELETE | `/games/:slug` | yes | Get / update / remove a game |
| GET/PUT | `/games/:slug/device` | yes | Per-device ROM + save paths |
| GET/POST | `/games/:slug/save` | yes | Pull / push save blob |
| GET | `/games/:slug/save/meta` | yes | Save hash + timestamp |
| POST/DELETE/GET | `/games/:slug/lock` | yes | Acquire / release / check lock |

Auth is `Authorization: Bearer <token>` obtained from `/pair`.

## Build AppImage (Linux)

```bash
./build-appimage.sh
# Output: gui/dist/EmuSync-*.AppImage
```

Requires: `pyinstaller` (`pip install pyinstaller`), `npm`

The AppImage bundles the Python backend — no Python required on the target machine.

## Testing

Run the full two-device sync test on a single machine:

```bash
bash test-sync.sh
```

Tests: pairing, game registration, save push/pull across devices, save versioning, lock contention.

## Key design decisions

- **No cloud.** mDNS only — devices find each other like printers on a LAN.
- **Lock stale after 4 hours** — a crashed session never blocks the other device forever.
- **Save backup on pull** — existing save is copied to `.bak` before overwrite.
- **`emusync run` always releases the lock**, even if the emulator crashes (via `try/finally`).
- **Remove game = remove from management only.** Files on disk are never deleted.
- **`EMUSYNC_CONFIG_DIR` env var** overrides the default `~/.emusync/` — used in tests to simulate multiple devices on one machine.
