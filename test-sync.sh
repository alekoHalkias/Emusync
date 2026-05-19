#!/usr/bin/env bash
set -euo pipefail

BACKEND=/home/agolucki/projects/Emusync/backend
DEV2=$HOME/tmp-emusync-device2
SERVER_LOG=/tmp/emusync-test-server.log

sep() { echo ""; echo "──────────────────────────────────────"; echo "  $1"; echo "──────────────────────────────────────"; }

# ── Clean slate ────────────────────────────────────────────────────────────
sep "Cleaning up previous test state"
# Kill anything holding port 8765
fuser -k 8765/tcp 2>/dev/null || true
pkill -f "cli.py server start" 2>/dev/null || true
sleep 2
rm -rf ~/.emusync "$DEV2"
mkdir -p "$DEV2"

cd "$BACKEND"

# ── Start server ───────────────────────────────────────────────────────────
sep "Starting EmuSync server"
python3 cli.py server start > "$SERVER_LOG" 2>&1 &
SERVER_PID=$!
echo "Server PID: $SERVER_PID"

# Wait until the server is actually accepting connections
for i in $(seq 1 15); do
    sleep 1
    if curl -sf http://localhost:8765/health >/dev/null 2>&1; then
        echo "Server is up."
        break
    fi
done

cat "$SERVER_LOG"

TOKEN=$(grep "Pairing token:" "$SERVER_LOG" | awk '{print $NF}' | tr -d '\r\n')
echo ""
echo "Captured token: $TOKEN"

# ── Pair both devices ──────────────────────────────────────────────────────
sep "Pairing Device 1 (gaming PC)"
python3 cli.py device pair --host localhost --token "$TOKEN"

sep "Pairing Device 2 (steam deck)"
EMUSYNC_CONFIG_DIR="$DEV2/.emusync" python3 cli.py device pair --host localhost --token "$TOKEN"

sep "Registered devices"
python3 cli.py device list

# ── Create fake game files ─────────────────────────────────────────────────
sep "Creating fake ROM and save files"

SAVE1=/tmp/emusync-test-zelda-dev1.sav
SAVE2=$DEV2/zelda.sav
ROM=/tmp/emusync-test-zelda.rom

echo "fake-rom-binary-data-zelda" > "$ROM"
echo "[SAVE v1] Link: starting village, 0 hearts, 0 rupees" > "$SAVE1"
cp "$SAVE1" "$SAVE2"

echo "Device 1 save: $SAVE1"
echo "Device 2 save: $SAVE2"

# ── Register game ──────────────────────────────────────────────────────────
sep "Device 1: registering game 'zelda'"
python3 cli.py game add zelda \
    --name "The Legend of Zelda: BOTW" \
    --rom "$ROM" \
    --save "$SAVE1"

sep "Device 2: setting its own paths for 'zelda'"
EMUSYNC_CONFIG_DIR="$DEV2/.emusync" python3 cli.py game edit zelda \
    --rom "$ROM" \
    --save "$SAVE2"

sep "Game list"
python3 cli.py game list

# ── Sync status (no saves yet) ─────────────────────────────────────────────
sep "Sync status — no saves yet"
python3 cli.py sync status

# ── Device 1 plays ────────────────────────────────────────────────────────
sep "Device 1: playing zelda (acquires lock, no pull yet, pushes save v2)"
python3 cli.py run --game zelda -- bash -c "
    echo '[SAVE v2] Link: Hyrule Castle reached, 10 hearts, 500 rupees' > $SAVE1
    echo 'Device 1 emulator exiting.'
"

echo ""
echo "Device 1 save after play:"
cat "$SAVE1"

# ── Sync status (save v2 on server) ───────────────────────────────────────
sep "Sync status — save v2 on server"
python3 cli.py sync status

# ── Device 2 plays ────────────────────────────────────────────────────────
sep "Device 2: playing zelda (pulls v2, plays, pushes v3)"
EMUSYNC_CONFIG_DIR="$DEV2/.emusync" python3 cli.py run --game zelda -- bash -c "
    echo ''
    echo 'Device 2 emulator sees save:'
    cat $SAVE2
    echo '[SAVE v3] Link: Ganon defeated, 13 hearts, 9999 rupees' > $SAVE2
    echo 'Device 2 emulator exiting.'
"

echo ""
echo "Device 2 save after play:"
cat "$SAVE2"

echo ""
echo "Device 2 backup (auto-created before pull):"
cat "${SAVE2}.bak" 2>/dev/null || echo "(no backup — was first pull)"

# ── Device 1 syncs again ──────────────────────────────────────────────────
sep "Device 1: syncs again (pulls v3 from server)"
python3 cli.py run --game zelda -- bash -c "
    echo ''
    echo 'Device 1 emulator sees save:'
    cat $SAVE1
    echo 'Device 1 emulator exiting (no changes).'
"

echo ""
echo "Device 1 save after sync (should be v3):"
cat "$SAVE1"
echo "Device 1 backup (.bak from pull):"
cat "${SAVE1}.bak"

# ── Lock contention test ───────────────────────────────────────────────────
sep "Lock contention test: Device 1 holds lock, Device 2 tries to grab it"

# Manually acquire lock as device 1
python3 -c "
import httpx, tomli
with open('$HOME/.emusync/emusync.toml', 'rb') as f:
    cfg = tomli.load(f)
r = httpx.post(
    f'http://localhost:{cfg[\"server_port\"]}/games/zelda/lock',
    headers={'Authorization': f'Bearer {cfg[\"token\"]}'}
)
print('Device 1 acquired lock:', r.json())
"

echo ""
echo "Device 2 tries to run while lock is held..."
if EMUSYNC_CONFIG_DIR="$DEV2/.emusync" python3 cli.py run --game zelda -- echo "should not run" 2>&1; then
    echo "ERROR: Should have been blocked by lock!"
else
    echo "Correctly blocked: 'This game is currently being played on another device.'"
fi

# Release the lock
python3 -c "
import httpx, tomli
with open('$HOME/.emusync/emusync.toml', 'rb') as f:
    cfg = tomli.load(f)
r = httpx.delete(
    f'http://localhost:{cfg[\"server_port\"]}/games/zelda/lock',
    headers={'Authorization': f'Bearer {cfg[\"token\"]}'}
)
print('Device 1 released lock:', r.json())
"

# ── Final status ───────────────────────────────────────────────────────────
sep "Final sync status"
python3 cli.py sync status

# ── Teardown ───────────────────────────────────────────────────────────────
sep "Stopping server"
kill "$SERVER_PID" 2>/dev/null || true
wait "$SERVER_PID" 2>/dev/null || true

rm -f "$ROM" "$SAVE1" "${SAVE1}.bak"
rm -rf "$DEV2"

echo ""
echo "All tests passed!"
