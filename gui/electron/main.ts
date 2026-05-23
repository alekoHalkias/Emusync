import { app, BrowserWindow, dialog, ipcMain, shell } from "electron";
import { spawn, execSync, ChildProcess } from "child_process";
import { existsSync, readFileSync, writeFileSync, unlinkSync, mkdirSync, readdirSync } from "fs";
import { join, dirname, basename, extname } from "path";
import { homedir } from "os";
import { parse as parseTOML, stringify as stringifyTOML } from "smol-toml";

const CONFIG_PATH = join(homedir(), ".emusync", "emusync.toml");
const SCRIPT = process.env.EMUSYNC_SCRIPT ?? join(__dirname, "../../../emusync.py");
const PYTHON = process.env.EMUSYNC_PYTHON ?? (() => {
  const venv = join(dirname(SCRIPT), ".venv", "bin", "python");
  return require("fs").existsSync(venv) ? venv : "python3";
})();

let serverProcess: ChildProcess | null = null;
let serverToken: string | null = null;
let gameProcess: ChildProcess | null = null;
let mainWindow: BrowserWindow | null = null;


function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 900,
    height: 650,
    minWidth: 700,
    minHeight: 500,
    title: "EmuSync",
    autoHideMenuBar: true,
    webPreferences: {
      preload: join(__dirname, "../preload/preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (process.env.NODE_ENV === "development") {
    mainWindow.loadURL("http://localhost:5173");
  } else {
    mainWindow.loadFile(join(__dirname, "../renderer/index.html"));
  }

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
}

// ── IPC handlers ──────────────────────────────────────────────────────────────

ipcMain.handle("config:load", () => {
  if (!existsSync(CONFIG_PATH)) return null;
  try {
    return parseTOML(readFileSync(CONFIG_PATH, "utf-8"));
  } catch {
    return null;
  }
});

ipcMain.handle("config:save", (_event, data: Record<string, unknown>) => {
  mkdirSync(dirname(CONFIG_PATH), { recursive: true });
  writeFileSync(CONFIG_PATH, stringifyTOML(data as any));
  return true;
});

ipcMain.handle("config:exists", () => existsSync(CONFIG_PATH));

function startServerProcess(): Promise<{ ok: boolean; token: string | null }> {
  if (serverProcess) return Promise.resolve({ ok: true, token: serverToken });

  return new Promise<{ ok: boolean; token: string | null }>((resolve) => {
    let token: string | null = null;
    const proc = spawn(PYTHON, [SCRIPT, "server", "start"], {
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
    });
    serverProcess = proc;

    proc.stdout?.on("data", (chunk: Buffer) => {
      const line = chunk.toString();
      const match = line.match(/Pairing token: (\S+)/);
      if (match) {
        token = match[1];
        serverToken = token;
        resolve({ ok: true, token });
      }
    });

    proc.on("error", (err) => {
      serverProcess = null;
      resolve({ ok: false, token: null });
      console.error("Server process error:", err);
    });

    proc.on("exit", () => {
      serverProcess = null;
      serverToken = null;
    });

    setTimeout(() => {
      if (token === null) resolve({ ok: true, token: null });
    }, 5000);
  });
}

ipcMain.handle("server:start", () => startServerProcess());

function killServerByPid(): void {
  const pidFile = join(homedir(), ".emusync", ".server_pid");
  try {
    if (existsSync(pidFile)) {
      const pid = parseInt(readFileSync(pidFile, "utf-8").trim(), 10);
      if (pid) try { process.kill(pid, "SIGKILL"); } catch {}
      unlinkSync(pidFile);
    }
  } catch {}
  try { unlinkSync(join(homedir(), ".emusync", ".server_token")); } catch {}
}

function killOrphanServers(): Promise<void> {
  return new Promise((resolve) => {
    // Kill any emusync server process not tracked by serverProcess (orphans from previous sessions)
    const proc = spawn("pkill", ["-9", "-f", "emusync.py server start"], { stdio: "ignore" });
    proc.on("exit", resolve);
    proc.on("error", resolve);
    setTimeout(resolve, 1000);
  });
}

ipcMain.handle("server:stop", async () => {
  if (serverProcess) {
    serverProcess.kill("SIGKILL");
    serverProcess = null;
  }
  serverToken = null;
  killServerByPid();
  await killOrphanServers();
  return true;
});

ipcMain.handle("server:token", () => {
  if (serverToken) return serverToken;
  const tokenFile = join(homedir(), ".emusync", ".server_token");
  try {
    if (existsSync(tokenFile)) return readFileSync(tokenFile, "utf-8").trim();
  } catch {}
  return null;
});

ipcMain.handle("server:discover", () => {
  return new Promise<Array<{ name: string; host: string; port: number }>>((resolve) => {
    const proc = spawn(PYTHON, [SCRIPT, "server", "discover-json"], {
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
    });
    let output = "";
    proc.stdout?.on("data", (chunk: Buffer) => { output += chunk.toString(); });
    proc.on("exit", () => { try { resolve(JSON.parse(output)); } catch { resolve([]); } });
    proc.on("error", () => resolve([]));
  });
});

ipcMain.handle("server:change-pin", async (_event, pin: string | null) => {
  // Stop running server
  if (serverProcess) {
    serverProcess.kill("SIGKILL");
    serverProcess = null;
  }
  serverToken = null;
  killServerByPid();
  await killOrphanServers();

  // Save PIN to config
  const raw = existsSync(CONFIG_PATH) ? parseTOML(readFileSync(CONFIG_PATH, "utf-8")) as Record<string, unknown> : {};
  if (pin) {
    raw.server_pin = pin;
  } else {
    delete raw.server_pin;
  }
  writeFileSync(CONFIG_PATH, stringifyTOML(raw as any));

  // Clear all paired devices so they must re-pair
  await new Promise<void>((resolve) => {
    const proc = spawn(PYTHON, [SCRIPT, "server", "clear-devices"], { stdio: "ignore" });
    proc.on("exit", () => resolve());
    proc.on("error", () => resolve());
  });

  return startServerProcess();
});

ipcMain.handle("launcher:path", () => join(dirname(SCRIPT), "emusync"));

ipcMain.handle("dialog:openFile", async (_event, options: Electron.OpenDialogOptions) => {
  const result = await dialog.showOpenDialog(mainWindow!, options);
  return result.canceled ? null : result.filePaths[0];
});

ipcMain.handle("game:launch", (_event, slug: string, command: string) => {
  if (gameProcess) return { ok: false };
  const args = (command.match(/(?:[^\s"']+|"[^"]*"|'[^']*')+/g) ?? [])
    .map(a => /^["']/.test(a) ? a.slice(1, -1) : a);
  const proc = spawn(PYTHON, [SCRIPT, "run", "--game", slug, "--", ...args], {
    stdio: "ignore",
    detached: true,
    env: { ...process.env, DISPLAY: process.env.DISPLAY || ":0", WAYLAND_DISPLAY: process.env.WAYLAND_DISPLAY || "wayland-0" },
  });
  gameProcess = proc;
  proc.on("exit", () => {
    gameProcess = null;
    mainWindow?.webContents.send("game:exited");
  });
  proc.unref();
  return { ok: true };
});

ipcMain.handle("game:stop", () => {
  if (gameProcess?.pid) {
    try { process.kill(-gameProcess.pid, "SIGTERM"); } catch { gameProcess.kill("SIGTERM"); }
    // Do NOT null gameProcess here — let the exit event do it so game:isRunning()
    // stays true while the Python wrapper is still in its finally block (releasing
    // the lock), preventing the lock-polling race that shows "Playing on Steam".
  }
  return { ok: true };
});

ipcMain.handle("game:isRunning", () => gameProcess !== null);

ipcMain.handle("game:stop-external", () => {
  const gamePidFile = join(homedir(), ".emusync", ".game_pid");
  try {
    if (existsSync(gamePidFile)) {
      const lines = readFileSync(gamePidFile, "utf-8").trim().split("\n");
      const emusyncPid = parseInt(lines[0], 10);
      const childPid = lines[1] ? parseInt(lines[1], 10) : NaN;
      if (childPid) try { process.kill(childPid, "SIGKILL"); } catch {}
      if (emusyncPid) try { process.kill(emusyncPid, "SIGTERM"); } catch {}
    }
  } catch {}
  return { ok: true };
});

ipcMain.handle("game:hasPidFile", () => {
  const gamePidFile = join(homedir(), ".emusync", ".game_pid");
  if (!existsSync(gamePidFile)) return false;
  try {
    const pid = parseInt(readFileSync(gamePidFile, "utf-8").trim().split("\n")[0], 10);
    if (!pid) return false;
    try { process.kill(pid, 0); } catch { return false; }
    // Verify the process is actually emusync, not a recycled PID
    try {
      const cmdline = readFileSync(`/proc/${pid}/cmdline`, "utf-8");
      return cmdline.includes("emusync") || cmdline.includes("python");
    } catch { return true; } // non-Linux: trust the signal check
  } catch { return false; }
});

// ── emulator scanning ─────────────────────────────────────────────────────────

const ROM_EXTENSIONS = new Set([
  "sfc", "smc",                        // SNES
  "gb", "gbc",                         // Game Boy / Color
  "gba",                               // Game Boy Advance
  "nes", "fds",                        // NES
  "n64", "z64", "v64",                 // Nintendo 64
  "nds",                               // Nintendo DS
  "md", "smd", "gen",                  // Sega Genesis / Mega Drive
  "sms", "gg",                         // Sega Master System / Game Gear
  "32x",                               // Sega 32X
  "pce",                               // PC Engine
  "ws", "wsc",                         // WonderSwan
  "ngp", "ngc",                        // Neo Geo Pocket
  "a26", "a52", "a78",                 // Atari
  "lnx",                               // Atari Lynx
  "iso", "cue", "bin", "chd", "pbp",   // Disc-based (PSX, Dreamcast…)
]);

const SAVE_EXTENSIONS = ["srm", "sav", "save"];

interface EmulatorInfo {
  type: "native" | "flatpak";
  label: string;      // display name, e.g. "RetroArch (Flatpak)"
  execPath: string;   // binary or "flatpak run ..."
  saveDir: string;
  romDirs: string[];
}

export interface RomEntry {
  name: string;
  romPath: string;
  savePath: string;       // predicted path, may not exist yet
  saveExists: boolean;
  launchCommand: string;
}

export interface EmulatorScanResult {
  emulators: EmulatorInfo[];
  romDirs: string[];      // dirs that were actually scanned
  roms: RomEntry[];
}

function parseRetroArchCfg(cfgPath: string): Record<string, string> {
  const out: Record<string, string> = {};
  if (!existsSync(cfgPath)) return out;
  for (const line of readFileSync(cfgPath, "utf-8").split("\n")) {
    const m = line.match(/^\s*(\w+)\s*=\s*"?([^"#\r\n]*)"?\s*$/);
    if (m) out[m[1].trim()] = m[2].trim();
  }
  return out;
}

function detectRetroArch(home: string): EmulatorInfo[] {
  const infos: EmulatorInfo[] = [];

  // ── native ──────────────────────────────────────────────────────────────────
  const nativeBins = ["/usr/bin/retroarch", "/usr/local/bin/retroarch", join(home, ".local/bin/retroarch")];
  const nativeCfg  = join(home, ".config/retroarch/retroarch.cfg");
  for (const bin of nativeBins) {
    if (existsSync(bin)) {
      const cfg = parseRetroArchCfg(nativeCfg);
      infos.push({
        type:    "native",
        label:   "RetroArch",
        execPath: bin,
        saveDir: cfg.savefile_directory || join(home, ".config/retroarch/saves"),
        romDirs: [cfg.rgui_browser_directory].filter(Boolean) as string[],
      });
      break;
    }
  }

  // ── flatpak ─────────────────────────────────────────────────────────────────
  try {
    const list = execSync("flatpak list --app --columns=application 2>/dev/null", { timeout: 5000 }).toString();
    if (list.includes("org.libretro.RetroArch")) {
      const flatCfg  = join(home, ".var/app/org.libretro.RetroArch/config/retroarch/retroarch.cfg");
      const cfg = parseRetroArchCfg(flatCfg);
      infos.push({
        type:    "flatpak",
        label:   "RetroArch (Flatpak)",
        execPath: "flatpak run org.libretro.RetroArch",
        saveDir: cfg.savefile_directory || join(home, ".var/app/org.libretro.RetroArch/config/retroarch/saves"),
        romDirs: [cfg.rgui_browser_directory].filter(Boolean) as string[],
      });
    }
  } catch { /* flatpak not available */ }

  return infos;
}

function scanRomDir(dir: string, depth = 0): string[] {
  if (depth > 3) return [];
  try {
    const entries = readdirSync(dir, { withFileTypes: true });
    const roms: string[] = [];
    for (const e of entries) {
      if (e.isFile() && ROM_EXTENSIONS.has(extname(e.name).slice(1).toLowerCase())) {
        roms.push(join(dir, e.name));
      } else if (e.isDirectory()) {
        roms.push(...scanRomDir(join(dir, e.name), depth + 1));
      }
    }
    return roms;
  } catch { return []; }
}

function matchSave(saveDir: string, baseName: string): { path: string; exists: boolean } {
  for (const ext of SAVE_EXTENSIONS) {
    const p = join(saveDir, `${baseName}.${ext}`);
    if (existsSync(p)) return { path: p, exists: true };
  }
  return { path: join(saveDir, `${baseName}.srm`), exists: false };
}

ipcMain.handle("emulator:scan", (_event, extraPaths: string[]): EmulatorScanResult => {
  const home    = homedir();
  const emus    = detectRetroArch(home);

  // Collect unique ROM dirs from all detected emulators + user-supplied extras
  const romDirs = [...new Set([
    ...emus.flatMap(e => e.romDirs),
    ...(extraPaths ?? []),
  ].filter(Boolean))];

  const roms: RomEntry[] = romDirs.flatMap(dir => {
    return scanRomDir(dir).map(romPath => {
      const base = basename(romPath, extname(romPath));

      // Match save against every detected emulator's save dir, prefer existing
      let savePath = "";
      let saveExists = false;
      for (const emu of emus) {
        const m = matchSave(emu.saveDir, base);
        if (m.exists) { savePath = m.path; saveExists = true; break; }
        if (!savePath) savePath = m.path; // take first predicted path as fallback
      }
      // If no emulator detected at all, predict alongside the ROM
      if (!savePath) savePath = join(dirname(romPath), `${base}.srm`);

      // Build launch command from whichever emulator was found first
      const launchCommand = emus.length
        ? `${emus[0].execPath} "${romPath}"`
        : "";

      return { name: base, romPath, savePath, saveExists, launchCommand };
    });
  });

  return { emulators: emus, romDirs, roms };
});

ipcMain.handle("dialog:openFolder", async () => {
  const result = await dialog.showOpenDialog(mainWindow!, { properties: ["openDirectory"] });
  return result.canceled ? null : result.filePaths[0];
});

// ── app lifecycle ─────────────────────────────────────────────────────────────

app.whenReady().then(() => {
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (serverProcess) {
    serverProcess.kill("SIGKILL");
    serverProcess = null;
  }
  killServerByPid();
  spawn("pkill", ["-9", "-f", "emusync.py server start"], { stdio: "ignore" });
  if (process.platform !== "darwin") app.quit();
});
