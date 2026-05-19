#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== EmuSync AppImage Builder ==="

# 1. Freeze Python backend with PyInstaller
echo ""
echo "[1/3] Building Python backend..."
bash "$ROOT/backend/build-backend.sh"

# 2. Install GUI deps if needed
echo ""
echo "[2/3] Installing GUI dependencies..."
cd "$ROOT/gui"
npm install --silent

# 3. Build AppImage
echo ""
echo "[3/3] Building AppImage..."
npm run dist

echo ""
echo "=== Done! ==="
echo "AppImage: $ROOT/gui/dist/*.AppImage"
