# EmuSync Summary

## What it does

Keeps emulator save files in sync across devices on a local network. Play a game on your PC, pick it up on your Steam Deck at the exact point you left off — no cloud, no subscription.

**Architecture**: One machine runs a Python/FastAPI server; other devices connect via mDNS and sync automatically through an Electron+React GUI that spawns the server process.

## Tech stack

- **Python 3.10+**: FastAPI backend, Click CLI
- **SQLite**: WAL-mode storage for saves/config
- **Electron 31 + React 18**: Cross-platform GUI
- **zconf/mDNS**: Service discovery on LAN
- **Key packages**: `uvicorn`, `to
