# EmuSync

LAN save-file sync for emulators. Keeps game saves in sync across devices (gaming PC ↔ Steam Deck) on a home network — no cloud, no accounts, no port forwarding.

---

## How it works

One machine runs the **server** (your gaming PC). Other devices **pair** with it over mDNS — no IP config needed. The `emusync run` wrapper pulls the latest save before launch and pushes it back after you quit. Locks prevent two devices from playing the same game at the same time.

---

## Project layout

```
emusync.py              ← CLI entry point (all commands live here)
emusync                 ← generated shell launcher (created by install.sh)
install.sh              ← one-shot setup script
Makefile                ← dev shortcuts
requirements.txt        ← Python deps
pyproject.toml          ← package metadata

server/
├── api.py              ← FastAPI REST API (all endpoints)
├── config.py           ← TOML config (~/.emusync/emusync.toml)
├── store.py            ← SQLite database (devices, games, saves, locks)
├── mdns.py             ← mDNS advertise + LAN discovery (zeroconf)
└── sync_client.py      ← HTTP client wrapping all server endpoints

gui/
├── electron/
│   ├── main.ts         ← Electron main process (spawns Python server, IPC)
│   └── preload.ts      ← contextBridge API exposed to renderer
├── renderer/
│   ├── index.html
│   └── src/
│       ├── App.tsx             ← root component, screen router
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
# Clone and install everything in one step
git clone https://github.com/alekoHalkias/Emusync
cd Emusync
bash install.sh
```

`install.sh` creates a Python venv at `.venv/`, installs all Python deps, installs Node deps in `gui/`, and generates an `emusync` launcher script.

---

## Running

### CLI

```bash
# On the server machine (gaming PC):
./emusync server start
# → prints: Pairing token: <uuid>

# On the client machine (Steam Deck / second device):
./emusync device pair --token <token>
# Auto-discovers server via mDNS. Use --host <ip> to specify manually.
```

### GUI (development)

```bash
# Terminal 1 — Python backend
./emusync server start

# Terminal 2 — Electron + Vite dev server
cd gui && npm run dev
```

### GUI (production build)

```bash
cd gui
npm run build      # compiles to out/
npx electron . --no-sandbox   # run it (--no-sandbox needed on WSL)
```

---

## CLI reference

```bash
./emusync server start

./emusync device pair [--host <ip>] [--port <port>] --token <token>
./emusync device list

./emusync game add [<slug>] --name "Game Name" [--rom <path>] [--save <path>] [--command <cmd>]
./emusync game list
./emusync game edit <slug> [--name] [--rom] [--save] [--command]
./emusync game remove <slug>

./emusync sync status

# Steam launch wrapper — add to Steam launch options:
./emusync run --game <slug> -- %command%
# e.g.: ./emusync run --game botw -- retroarch -L switch.so game.nsp
```

---

## REST API

Server runs on port `8765` by default. Auth is `Authorization: Bearer <token>`.

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/health` | no | Health check |
| POST | `/pair` | no | Pair a device (requires master token) |
| GET | `/devices` | yes | List paired devices |
| GET/POST | `/games` | yes | List / add games |
| GET/PUT/DELETE | `/games/:slug` | yes | Get / update / remove a game |
| GET/PUT | `/games/:slug/device` | yes | Per-device ROM + save paths |
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

Set `EMUSYNC_CONFIG_DIR` to override the config directory (used in tests to simulate multiple devices on one machine).

---

## Makefile shortcuts

```bash
make install      # run install.sh
make dev-server   # start Python backend via venv
make dev-gui      # cd gui && npm run dev
make build-gui    # cd gui && npm run build
make lint         # syntax-check all Python files
```

---

## Key design decisions

- **No cloud.** mDNS only — devices find each other like a printer on your LAN.
- **Lock stale after 4 hours** — a crashed session never blocks the other device forever.
- **Save backup on pull** — existing save copied to `.bak` before overwrite.
- **`emusync run` always releases the lock** even if the emulator crashes (`try/finally`).
- **Remove game = remove from management only.** Files on disk are never deleted.
- **GUI and CLI are equivalent.** Everything in the GUI is also a CLI command.
- **Electron main reads/writes config directly** via `smol-toml` — no round-trip to the Python server needed for setup.
