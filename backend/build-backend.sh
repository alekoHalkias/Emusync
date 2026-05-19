#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "==> Installing PyInstaller..."
python3 -m pip install pyinstaller --quiet

echo "==> Building backend binary..."
python3 -m PyInstaller \
  --onefile \
  --name emusync-backend \
  --collect-all uvicorn \
  --collect-all fastapi \
  --collect-submodules zeroconf \
  --hidden-import tomli \
  --hidden-import tomli_w \
  --hidden-import httpx \
  --hidden-import click \
  cli.py

echo "==> Backend binary: dist/emusync-backend"
