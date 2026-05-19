# EmuSync

Keep your emulator save files in sync across your devices on your home network — no cloud accounts, no port forwarding, no subscription. Play a game on your gaming PC, pick it up on your Steam Deck right where you left off.

One machine (your gaming PC) runs the server. Every other device on your LAN connects to it and stays in sync automatically.

---

## Requirements

- Python 3.10 or newer
- Node.js 18 or newer + npm
- Git

---

## Install from source

```bash
git clone https://github.com/alekoHalkias/Emusync
cd Emusync
bash install.sh
```

`install.sh` does everything in one shot:
- Creates a Python virtual environment (`.venv/`)
- Installs all Python dependencies
- Installs Node dependencies for the GUI
- Writes an `emusync` launcher script in the repo root

After that, the GUI is ready and the `emusync` command is available inside the project directory.

---

## First-time setup

EmuSync has two roles — **server** and **client**. Your gaming PC is the server. Your Steam Deck (or any other machine) is a client.

### On your gaming PC (server)

Open the GUI:

```bash
cd gui && npm run dev
```

On first launch you'll see a setup screen. Enter a name for this machine (e.g. `Gaming PC`) and choose **Set up this as the server**. The server will start automatically.

If you want to require a PIN before other devices can connect, open the **Server online** button in the top right after setup and set a 4-digit PIN. If you leave it blank, any device on your LAN can connect without a code.

### On your Steam Deck or second device (client)

Open the GUI the same way, choose **Join an existing server**, and enter:

- **Server host** — the local IP of your gaming PC (e.g. `192.168.1.50`)
- **Port** — `8765` (default)
- **PIN** — the PIN you set on the server, or leave blank if none was set

That's it. The device is now paired and will sync saves through the server.

---

## Using the GUI

Launch the GUI from the repo root:

```bash
cd gui && npm run dev
```

### Adding a game

Click **Add game** and fill in:

| Field | What to enter |
|-------|--------------|
| Name | Anything you want, e.g. `Pokemon Emerald` |
| ROM path | Full path to your ROM file |
| Save path | Full path to the save file your emulator writes |
| Launch command | The full command that opens the emulator with this ROM |

**RetroArch example:**
```
retroarch -L /usr/lib/x86_64-linux-gnu/libretro/mgba_libretro.so "/home/user/roms/emerald.gba"
```

RetroArch saves GBA games as `.srm` files (not `.sav`). Look for it in your RetroArch saves folder.

### Playing a game

Click the **▶** button next to a game. EmuSync will:
1. Pull the latest save from the server (overwriting your local file)
2. Launch the emulator
3. Push your save back to the server when you quit

If another device is currently playing that game, EmuSync will block the launch to prevent save conflicts.

### Server controls (top-right button)

Click the **Server online / Server offline** button to open the server panel:

- **Start / Stop server** — start or shut down the server on this machine
- **Server name** — change how this machine appears to other devices
- **PIN** — set or clear a 4-digit PIN that clients must enter to connect. Changing the PIN restarts the server and disconnects all paired devices — they'll need to re-pair.
- **Re-pair this device / Connect to server** — switch which server this machine is connected to, or re-authenticate after a PIN change

---

## CLI reference

All CLI commands use the Python virtual environment:

```bash
.venv/bin/python emusync.py <command>
```

Or if you have the launcher script: `./emusync <command>`

---

### Server commands

#### `server start`
Starts the EmuSync server on this machine. Run this on your gaming PC if you're not using the GUI.

```bash
.venv/bin/python emusync.py server start
```

The server listens on port `8765` and advertises itself on the LAN so other devices can find it. If you've set a PIN in the config, it's used as the pairing code. Leave it blank and any device can pair without a code.

#### `server clear-devices`
Kicks all paired devices off the server. They'll need to re-pair before they can sync again. Useful if you've changed your PIN or a device is no longer yours.

```bash
.venv/bin/python emusync.py server clear-devices
```

---

### Device commands

#### `device pair`
Pairs this machine with an EmuSync server. Use this on your Steam Deck or second PC if you prefer the CLI over the GUI setup screen.

```bash
.venv/bin/python emusync.py device pair --host 192.168.1.50 --token 1234
```

| Flag | Description |
|------|-------------|
| `--host` | IP address of the server machine |
| `--port` | Port (default: `8765`) |
| `--token` | PIN set on the server, or omit if no PIN |

#### `device list`
Shows every device that's currently paired with the server. Useful for checking what's connected or cleaning up old devices.

```bash
.venv/bin/python emusync.py device list
```

---

### Game commands

#### `game add`
Registers a game with EmuSync so it can be synced. You'll do this once per game.

```bash
.venv/bin/python emusync.py game add --name "Pokemon Emerald" \
  --rom "/home/user/roms/emerald.gba" \
  --save "/home/user/.config/retroarch/saves/emerald.srm" \
  --command "retroarch -L /path/to/mgba_libretro.so /home/user/roms/emerald.gba"
```

| Flag | Description |
|------|-------------|
| `--name` | Display name for the game |
| `--rom` | Path to the ROM file |
| `--save` | Path to the save file your emulator writes |
| `--command` | Full launch command for the emulator |

#### `game list`
Lists all games registered with EmuSync, including their slugs (short IDs used in other commands).

```bash
.venv/bin/python emusync.py game list
```

#### `game edit`
Updates the name or paths for a game — handy if you moved your ROMs or switched emulators.

```bash
.venv/bin/python emusync.py game edit pokemon-emerald \
  --save "/new/path/to/emerald.srm"
```

Pass any combination of `--name`, `--rom`, `--save`, `--command`.

#### `game remove`
Removes a game from EmuSync management. This does **not** delete your ROM or save files — it just stops EmuSync from tracking it.

```bash
.venv/bin/python emusync.py game remove pokemon-emerald
```

---

### Run command

#### `run`
The heart of EmuSync. Pulls your save from the server, launches the emulator, then pushes the save back when you quit. This is what runs in the background every time you hit Play in the GUI.

```bash
.venv/bin/python emusync.py run --game pokemon-emerald -- retroarch -L /path/to/core.so /path/to/rom.gba
```

Everything after `--` is the emulator command. EmuSync wraps it and handles the sync automatically.

**Steam integration** — paste this into Steam → game properties → launch options:

```
/path/to/emusync run --game your-game-slug -- %command%
```

Steam will pass the game's own launch command as `%command%`, and EmuSync will wrap it.

---

### Sync commands

#### `sync status`
Shows the current lock and save status for every managed game. Useful for checking if a save is stuck locked (e.g. after a crash) or seeing which device last pushed a save and when.

```bash
.venv/bin/python emusync.py sync status
```

---

## Troubleshooting

**Save stuck locked after a crash** — if EmuSync or the emulator was force-killed, the game might show as locked. Restart the server to clear all locks, or wait — locks expire automatically after 4 hours.

**"Server offline" even though the server is running** — check that both devices are on the same local network and that nothing is blocking port `8765`. The server must be started before the client can connect.

**WSL2 display issues** — the GUI requires a display server. Make sure `DISPLAY=:0` is set in your environment. The dev script handles this automatically.

**Stale database after an update** — if you see a database error after pulling a new version, delete the old DB and restart: `rm ~/.emusync/emusync.db`. Your game list will need to be re-added but your ROM and save files are untouched.

---

## Uninstall

1. Stop the server if it's running (click **Stop server** in the GUI or Ctrl-C in the terminal)
2. Delete the repo:
   ```bash
   rm -rf /path/to/Emusync
   ```
3. Delete EmuSync's data folder (saves the server has stored, config, database):
   ```bash
   rm -rf ~/.emusync
   ```

That's everything. No system files are written outside the repo and `~/.emusync`.
