import { app, BrowserWindow, dialog, ipcMain, shell } from "electron";
import { spawn, execSync, ChildProcess } from "child_process";
import { existsSync, readFileSync, writeFileSync, unlinkSync, mkdirSync, readdirSync, statSync, createReadStream, renameSync } from "fs";
import { request as httpRequest } from "http";
import { join, dirname, basename, extname } from "path";
import { homedir, networkInterfaces } from "os";
import { parse as parseTOML, stringify as stringifyTOML } from "smol-toml";

const CONFIG_PATH = join(homedir(), ".emusync", "emusync.toml");
const SCRIPT = process.env.EMUSYNC_SCRIPT ?? join(__dirname, "../../../emusync.py");
const PYTHON = process.env.EMUSYNC_PYTHON ?? (() => {
  const venv = join(dirname(SCRIPT), ".venv", "bin", "python");
  return require("fs").existsSync(venv) ? venv : "python3";
})();

let serverProcess: ChildProcess | null = null;
let serverStartedByApp = false;
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

ipcMain.handle("config:getRecentFolders", (_event, consoleKey: string) => {
  if (!existsSync(CONFIG_PATH)) return [];
  try {
    const data = parseTOML(readFileSync(CONFIG_PATH, "utf-8"));
    const recentFolders = (data.recent_import_folders as Record<string, any>) || {};
    return recentFolders[consoleKey] || [];
  } catch {
    return [];
  }
});

ipcMain.handle("config:addRecentFolder", (_event, consoleKey: string, folderPath: string) => {
  if (!existsSync(CONFIG_PATH)) return;
  try {
    const data = parseTOML(readFileSync(CONFIG_PATH, "utf-8"));
    if (!data.recent_import_folders) {
      data.recent_import_folders = {};
    }
    const recentFolders = (data.recent_import_folders as Record<string, any>);
    if (!recentFolders[consoleKey]) {
      recentFolders[consoleKey] = [];
    }
    const folders = recentFolders[consoleKey] as string[];
    // Remove if already exists (will re-add at start)
    const index = folders.indexOf(folderPath);
    if (index !== -1) {
      folders.splice(index, 1);
    }
    // Add to front and limit to 10 recent folders
    folders.unshift(folderPath);
    folders.splice(10);
    writeFileSync(CONFIG_PATH, stringifyTOML(data as any));
  } catch {
    // ignore
  }
});

function startServerProcess(): Promise<{ ok: boolean }> {
  if (serverProcess) return Promise.resolve({ ok: true });

  return new Promise<{ ok: boolean }>((resolve) => {
    let resolved = false;
    const proc = spawn(PYTHON, [SCRIPT, "server", "start"], {
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
    });
    serverProcess = proc;

    // Resolve as soon as the server prints its startup line (before uvicorn binds)
    proc.stdout?.on("data", (chunk: Buffer) => {
      const line = chunk.toString();
      if (!resolved && line.includes("EmuSync server ready")) {
        resolved = true;
        serverStartedByApp = true; // Server actually started; only kill it on close if we started it
        resolve({ ok: true });
      }
    });

    proc.on("error", (err) => {
      serverProcess = null;
      if (!resolved) { resolved = true; resolve({ ok: false }); }
      console.error("Server process error:", err);
    });

    proc.on("exit", () => {
      serverProcess = null;
    });

    // Fallback: resolve after 5 s if we never see the startup line
    setTimeout(() => {
      if (!resolved) { resolved = true; resolve({ ok: true }); }
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
  killServerByPid();
  await killOrphanServers();
  serverStartedByApp = false; // User explicitly stopped the server
  return true;
});

ipcMain.handle("server:token", () => null); // deprecated — PIN auth no longer uses per-device tokens

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

ipcMain.handle("server:local-ip", (): string | null => {
  const nets = networkInterfaces();
  for (const name of Object.keys(nets)) {
    for (const iface of nets[name] ?? []) {
      if (iface.family === "IPv4" && !iface.internal) return iface.address;
    }
  }
  return null;
});

ipcMain.handle("server:change-pin", async (_event, pin: string | null) => {
  // Stop running server
  if (serverProcess) {
    serverProcess.kill("SIGKILL");
    serverProcess = null;
  }
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
  "iso", "cue", "bin", "chd", "pbp",   // Disc-based (PSX, Dreamcast, PSP…)
]);

// Per-core info: library filename (without .so) and the folder name RetroArch
// uses under saves/ when "Sort Saves by Core" is enabled.
interface CoreInfo {
  libName: string;      // e.g. "mgba_libretro"
  folderName: string;   // e.g. "mGBA"
}

interface SystemInfo {
  name: string;         // display name shown in the import UI
  saveExts: string[];   // save file extensions, most-likely first
  cores: CoreInfo[];    // preferred RetroArch cores, in order
}

const DEFAULT_SAVE_EXTS = ["srm", "sav", "save"];
const DEFAULT_STATE_EXTS = ["state", "state.auto"];

// Map ROM extension → system + preferred cores.  Cores are tried in order;
// the first one whose .so exists in the RetroArch cores directory wins.
const SYSTEMS: Record<string, SystemInfo> = {
  // ── Game Boy family ────────────────────────────────────────────────────────
  gba: {
    name: "Game Boy Advance",
    saveExts: ["sav", "srm"],
    cores: [
      { libName: "mgba_libretro",     folderName: "mGBA" },
      { libName: "vba_next_libretro", folderName: "VBA Next" },
      { libName: "vbam_libretro",     folderName: "VBA-M" },
    ],
  },
  gb: {
    name: "Game Boy",
    saveExts: ["sav", "srm"],
    cores: [
      { libName: "gambatte_libretro", folderName: "Gambatte" },
      { libName: "mgba_libretro",     folderName: "mGBA" },
      { libName: "gearboy_libretro",  folderName: "Gearboy" },
    ],
  },
  gbc: {
    name: "Game Boy Color",
    saveExts: ["sav", "srm"],
    cores: [
      { libName: "gambatte_libretro", folderName: "Gambatte" },
      { libName: "mgba_libretro",     folderName: "mGBA" },
      { libName: "gearboy_libretro",  folderName: "Gearboy" },
    ],
  },
  // ── SNES ──────────────────────────────────────────────────────────────────
  sfc: {
    name: "SNES",
    saveExts: ["srm", "sav"],
    cores: [
      { libName: "snes9x_libretro",     folderName: "Snes9x" },
      { libName: "bsnes_libretro",      folderName: "bsnes" },
      { libName: "snes9x2010_libretro", folderName: "Snes9x 2010" },
    ],
  },
  smc: {
    name: "SNES",
    saveExts: ["srm", "sav"],
    cores: [
      { libName: "snes9x_libretro",     folderName: "Snes9x" },
      { libName: "bsnes_libretro",      folderName: "bsnes" },
      { libName: "snes9x2010_libretro", folderName: "Snes9x 2010" },
    ],
  },
  // ── NES ───────────────────────────────────────────────────────────────────
  nes: {
    name: "NES",
    saveExts: ["sav", "srm"],
    cores: [
      { libName: "nestopia_libretro", folderName: "Nestopia UE" },
      { libName: "fceumm_libretro",   folderName: "FCEUmm" },
      { libName: "mesen_libretro",    folderName: "Mesen" },
    ],
  },
  fds: {
    name: "Famicom Disk System",
    saveExts: ["sav", "srm"],
    cores: [
      { libName: "nestopia_libretro", folderName: "Nestopia UE" },
      { libName: "fceumm_libretro",   folderName: "FCEUmm" },
    ],
  },
  // ── Nintendo 64 ───────────────────────────────────────────────────────────
  n64: {
    name: "Nintendo 64",
    saveExts: ["srm", "sav", "eep", "mpk"],
    cores: [
      { libName: "mupen64plus_next_libretro", folderName: "Mupen64Plus-Next" },
      { libName: "parallel_n64_libretro",     folderName: "ParaLLEl N64" },
    ],
  },
  z64: {
    name: "Nintendo 64",
    saveExts: ["srm", "sav", "eep", "mpk"],
    cores: [
      { libName: "mupen64plus_next_libretro", folderName: "Mupen64Plus-Next" },
      { libName: "parallel_n64_libretro",     folderName: "ParaLLEl N64" },
    ],
  },
  v64: {
    name: "Nintendo 64",
    saveExts: ["srm", "sav", "eep", "mpk"],
    cores: [
      { libName: "mupen64plus_next_libretro", folderName: "Mupen64Plus-Next" },
      { libName: "parallel_n64_libretro",     folderName: "ParaLLEl N64" },
    ],
  },
  // ── Nintendo DS ───────────────────────────────────────────────────────────
  nds: {
    name: "Nintendo DS",
    saveExts: ["sav", "dsv", "srm"],
    cores: [
      { libName: "melonds_libretro",     folderName: "melonDS" },
      { libName: "desmume_libretro",     folderName: "DeSmuME" },
      { libName: "desmume2015_libretro", folderName: "DeSmuME 2015" },
    ],
  },
  // ── Sega Genesis / Mega Drive ─────────────────────────────────────────────
  md:  {
    name: "Sega Genesis",
    saveExts: ["srm", "sav"],
    cores: [
      { libName: "genesis_plus_gx_libretro", folderName: "Genesis Plus GX" },
      { libName: "picodrive_libretro",       folderName: "PicoDrive" },
    ],
  },
  smd: {
    name: "Sega Genesis",
    saveExts: ["srm", "sav"],
    cores: [
      { libName: "genesis_plus_gx_libretro", folderName: "Genesis Plus GX" },
      { libName: "picodrive_libretro",       folderName: "PicoDrive" },
    ],
  },
  gen: {
    name: "Sega Genesis",
    saveExts: ["srm", "sav"],
    cores: [
      { libName: "genesis_plus_gx_libretro", folderName: "Genesis Plus GX" },
      { libName: "picodrive_libretro",       folderName: "PicoDrive" },
    ],
  },
  // ── Sega Master System / Game Gear ────────────────────────────────────────
  sms: {
    name: "Sega Master System",
    saveExts: ["srm", "sav"],
    cores: [
      { libName: "genesis_plus_gx_libretro", folderName: "Genesis Plus GX" },
      { libName: "picodrive_libretro",       folderName: "PicoDrive" },
    ],
  },
  gg: {
    name: "Game Gear",
    saveExts: ["srm", "sav"],
    cores: [
      { libName: "genesis_plus_gx_libretro", folderName: "Genesis Plus GX" },
    ],
  },
  // ── PC Engine ─────────────────────────────────────────────────────────────
  pce: {
    name: "PC Engine",
    saveExts: ["srm", "sav"],
    cores: [
      { libName: "mednafen_pce_libretro",      folderName: "Beetle PCE" },
      { libName: "mednafen_pce_fast_libretro", folderName: "Beetle PCE Fast" },
    ],
  },
  // ── Disc-based (PSX / Dreamcast / PSP) ───────────────────────────────────
  iso: {
    name: "Disc",
    saveExts: ["mcr", "srm", "sav"],
    cores: [
      { libName: "pcsx_rearmed_libretro",    folderName: "PCSX-ReARMed" },
      { libName: "mednafen_psx_libretro",    folderName: "Beetle PSX" },
      { libName: "mednafen_psx_hw_libretro", folderName: "Beetle PSX HW" },
      { libName: "flycast_libretro",         folderName: "Flycast" },
      { libName: "ppsspp_libretro",          folderName: "PPSSPP" },
    ],
  },
  bin: {
    name: "Disc",
    saveExts: ["mcr", "srm", "sav"],
    cores: [
      { libName: "pcsx_rearmed_libretro",    folderName: "PCSX-ReARMed" },
      { libName: "mednafen_psx_libretro",    folderName: "Beetle PSX" },
    ],
  },
  cue: {
    name: "Disc",
    saveExts: ["mcr", "srm", "sav"],
    cores: [
      { libName: "pcsx_rearmed_libretro",    folderName: "PCSX-ReARMed" },
      { libName: "mednafen_psx_libretro",    folderName: "Beetle PSX" },
    ],
  },
  chd: {
    name: "Disc (CHD)",
    saveExts: ["mcr", "srm", "sav"],
    cores: [
      { libName: "pcsx_rearmed_libretro",    folderName: "PCSX-ReARMed" },
      { libName: "mednafen_psx_libretro",    folderName: "Beetle PSX" },
      { libName: "flycast_libretro",         folderName: "Flycast" },
    ],
  },
  pbp: {
    name: "PSP / PS1",
    saveExts: ["srm", "sav", "mcr"],
    cores: [
      { libName: "ppsspp_libretro",       folderName: "PPSSPP" },
      { libName: "pcsx_rearmed_libretro", folderName: "PCSX-ReARMed" },
    ],
  },
};

interface EmulatorInfo {
  type: "native" | "flatpak";
  label: string;      // display name, e.g. "RetroArch (Flatpak)"
  execPath: string;   // binary path or "flatpak run ..."
  saveDir: string;    // root saves directory
  statesDir: string;  // root states directory
  coresDir: string;   // where core .so files live
  romDirs: string[];
}

export interface RomEntry {
  name: string;
  romPath: string;
  savePath: string;       // resolved path (may not exist yet)
  saveExists: boolean;
  statePath?: string;     // resolved state path (may not exist yet)
  stateExists?: boolean;
  launchCommand: string;
  consoleName?: string;   // e.g. "Game Boy Advance"
  coreName?: string;      // e.g. "mGBA" — the core that will be used
}

export interface EmulatorScanResult {
  emulators: EmulatorInfo[];
  romDirs: string[];
  roms: RomEntry[];
}

function parseRetroArchCfg(cfgPath: string, home: string): Record<string, string> {
  const out: Record<string, string> = {};
  if (!existsSync(cfgPath)) return out;
  // Node.js doesn't expand ~ — do it here so all path fields are absolute
  const expandHome = (v: string) => v.startsWith("~/") ? join(home, v.slice(2)) : v === "~" ? home : v;
  for (const line of readFileSync(cfgPath, "utf-8").split("\n")) {
    const m = line.match(/^\s*(\w+)\s*=\s*"?([^"#\r\n]*)"?\s*$/);
    if (m) out[m[1].trim()] = expandHome(m[2].trim());
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
      const cfg = parseRetroArchCfg(nativeCfg, home);
      // Filter out RetroArch's "default" placeholder (means "not configured")
      const romDir = cfg.rgui_browser_directory && cfg.rgui_browser_directory !== "default"
        ? cfg.rgui_browser_directory : "";
      infos.push({
        type:     "native",
        label:    "RetroArch",
        execPath:  bin,
        saveDir:   cfg.savefile_directory || join(home, ".config/retroarch/saves"),
        statesDir: cfg.savestate_directory || join(home, ".config/retroarch/states"),
        coresDir:  cfg.libretro_directory  || join(home, ".config/retroarch/cores"),
        romDirs:  [romDir].filter(Boolean) as string[],
      });
      break;
    }
  }

  // ── flatpak ─────────────────────────────────────────────────────────────────
  try {
    const list = execSync("flatpak list --app --columns=application 2>/dev/null", { timeout: 5000 }).toString();
    if (list.includes("org.libretro.RetroArch")) {
      const flatCfg = join(home, ".var/app/org.libretro.RetroArch/config/retroarch/retroarch.cfg");
      const cfg = parseRetroArchCfg(flatCfg, home);
      const flatRomDir = cfg.rgui_browser_directory && cfg.rgui_browser_directory !== "default"
        ? cfg.rgui_browser_directory : "";
      infos.push({
        type:     "flatpak",
        label:    "RetroArch (Flatpak)",
        execPath: "flatpak run org.libretro.RetroArch",
        saveDir:  cfg.savefile_directory || join(home, ".var/app/org.libretro.RetroArch/config/retroarch/saves"),
        statesDir: cfg.savestate_directory || join(home, ".var/app/org.libretro.RetroArch/config/retroarch/states"),
        coresDir: cfg.libretro_directory  || join(home, ".var/app/org.libretro.RetroArch/data/retroarch/cores"),
        romDirs:  [flatRomDir].filter(Boolean) as string[],
      });
    }
  } catch { /* flatpak not available */ }

  return infos;
}

/** Find the first installed core for a system in the given coresDir. */
function findInstalledCore(coresDir: string, system: SystemInfo): { lib: string; folderName: string } | null {
  for (const core of system.cores) {
    const soPath = join(coresDir, `${core.libName}.so`);
    if (existsSync(soPath)) return { lib: soPath, folderName: core.folderName };
  }
  return null;
}

/**
 * If a per-core subfolder exists inside saveDir (case-insensitive match on
 * folderName), return that subfolder path.  Otherwise return saveDir itself.
 */
function resolveCoreSaveDir(saveDir: string, coreFolderName: string): string {
  if (!existsSync(saveDir)) return saveDir;
  try {
    const entries = readdirSync(saveDir, { withFileTypes: true });
    const match = entries.find(
      e => e.isDirectory() && e.name.toLowerCase() === coreFolderName.toLowerCase()
    );
    if (match) return join(saveDir, match.name);
  } catch {}
  return saveDir;
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

/** Search saveDir for a file matching baseName + any of the given extensions. */
function matchSaveFile(saveDir: string, baseName: string, exts: string[]): { path: string; exists: boolean } {
  for (const ext of exts) {
    const p = join(saveDir, `${baseName}.${ext}`);
    if (existsSync(p)) return { path: p, exists: true };
  }
  return { path: join(saveDir, `${baseName}.${exts[0]}`), exists: false };
}

// ── console / emulator detection ──────────────────────────────────────────────

interface StandaloneDef {
  id: string;
  label: string;
  nativeBins: string[];
  flatpakId?: string;
  flatpakExec?: string;
  getDefaultSaveDir: (home: string) => string;
}

interface ConsoleDef {
  key: string;
  label: string;
  systemKeys: string[];       // ROM extensions covered by this console
  standalones: StandaloneDef[];
  suggestions: string[];      // shown when no emulators are detected
}

export interface DetectedEmulatorOption {
  id: string;
  label: string;
  execPath: string;
  saveDir: string;
  stateDir?: string;
  corePath?: string;
  coreFolderName?: string;
  romDirs: string[];
}

const CONSOLES: ConsoleDef[] = [
  {
    key: "gba",
    label: "Game Boy Advance",
    systemKeys: ["gba"],
    standalones: [
      {
        id: "mgba", label: "mGBA",
        nativeBins: ["/usr/bin/mgba-qt", "/usr/bin/mgba", join(homedir(), ".local/bin/mgba-qt")],
        flatpakId: "io.mgba.mGBA", flatpakExec: "flatpak run io.mgba.mGBA",
        getDefaultSaveDir: (h) => join(h, ".local/share/mGBA/saves"),
      },
    ],
    suggestions: ["RetroArch with mGBA core", "mGBA standalone"],
  },
  {
    key: "gb",
    label: "Game Boy / Game Boy Color",
    systemKeys: ["gb", "gbc"],
    standalones: [
      {
        id: "mgba", label: "mGBA",
        nativeBins: ["/usr/bin/mgba-qt", "/usr/bin/mgba"],
        flatpakId: "io.mgba.mGBA", flatpakExec: "flatpak run io.mgba.mGBA",
        getDefaultSaveDir: (h) => join(h, ".local/share/mGBA/saves"),
      },
    ],
    suggestions: ["RetroArch with Gambatte or mGBA core", "mGBA standalone"],
  },
  {
    key: "snes",
    label: "Super Nintendo (SNES)",
    systemKeys: ["sfc", "smc"],
    standalones: [],
    suggestions: ["RetroArch with Snes9x core"],
  },
  {
    key: "nes",
    label: "NES / Famicom",
    systemKeys: ["nes", "fds"],
    standalones: [],
    suggestions: ["RetroArch with Nestopia UE or FCEUmm core"],
  },
  {
    key: "n64",
    label: "Nintendo 64",
    systemKeys: ["n64", "z64", "v64"],
    standalones: [],
    suggestions: ["RetroArch with Mupen64Plus-Next core"],
  },
  {
    key: "nds",
    label: "Nintendo DS",
    systemKeys: ["nds"],
    standalones: [],
    suggestions: ["RetroArch with melonDS or DeSmuME core"],
  },
  {
    key: "genesis",
    label: "Sega Genesis / Mega Drive",
    systemKeys: ["md", "smd", "gen"],
    standalones: [],
    suggestions: ["RetroArch with Genesis Plus GX core"],
  },
  {
    key: "sms",
    label: "Master System / Game Gear",
    systemKeys: ["sms", "gg"],
    standalones: [],
    suggestions: ["RetroArch with Genesis Plus GX core"],
  },
  {
    key: "pce",
    label: "PC Engine",
    systemKeys: ["pce"],
    standalones: [],
    suggestions: ["RetroArch with Beetle PCE core"],
  },
  {
    key: "psx",
    label: "PlayStation",
    systemKeys: ["iso", "bin", "cue", "chd", "pbp"],
    standalones: [],
    suggestions: ["RetroArch with PCSX-ReARMed or Beetle PSX core"],
  },
];

function detectEmulatorsForConsole(home: string, consoleKey: string): DetectedEmulatorOption[] {
  const consoleDef = CONSOLES.find(c => c.key === consoleKey);
  if (!consoleDef) return [];
  const options: DetectedEmulatorOption[] = [];

  // ── RetroArch (native + flatpak) ──────────────────────────────────────────
  for (const ra of detectRetroArch(home)) {
    const seenCores = new Set<string>();
    for (const sysKey of consoleDef.systemKeys) {
      const sys = SYSTEMS[sysKey];
      if (!sys) continue;
      const core = findInstalledCore(ra.coresDir, sys);
      if (!core || seenCores.has(core.lib)) continue;
      seenCores.add(core.lib);
      const saveDir = join(ra.saveDir, core.folderName);
      const stateDir = join(ra.statesDir, core.folderName);
      options.push({
        id: `${ra.type}-${core.folderName.toLowerCase().replace(/[^a-z0-9]/g, "-")}`,
        label: `${ra.label} · ${core.folderName}`,
        execPath: ra.execPath,
        saveDir,
        stateDir,
        corePath: core.lib,
        coreFolderName: core.folderName,
        romDirs: ra.romDirs,
      });
    }
  }

  // ── Standalone emulators ──────────────────────────────────────────────────
  let flatpakList: string | null = null;
  const getFlatpakList = () => {
    if (flatpakList !== null) return flatpakList;
    try { flatpakList = execSync("flatpak list --app --columns=application 2>/dev/null", { timeout: 5000 }).toString(); }
    catch { flatpakList = ""; }
    return flatpakList;
  };

  for (const s of consoleDef.standalones) {
    let found = false;
    for (const bin of s.nativeBins) {
      if (existsSync(bin)) {
        options.push({ id: `${s.id}-native`, label: s.label, execPath: bin,
          saveDir: s.getDefaultSaveDir(home), romDirs: [] });
        found = true; break;
      }
    }
    if (!found && s.flatpakId && s.flatpakExec && getFlatpakList().includes(s.flatpakId)) {
      options.push({
        id: `${s.id}-flatpak`, label: `${s.label} (Flatpak)`,
        execPath: s.flatpakExec,
        saveDir: join(home, `.var/app/${s.flatpakId}/data/${s.id}/saves`),
        romDirs: [],
      });
    }
  }

  return options;
}

// ── IPC: console-based emulator import ────────────────────────────────────────

ipcMain.handle("emulator:consoles", () =>
  CONSOLES.map(c => ({ key: c.key, label: c.label }))
);

ipcMain.handle("emulator:detect", (_event, consoleKey: string): {
  options: DetectedEmulatorOption[];
  suggestions: string[];
} => {
  const consoleDef = CONSOLES.find(c => c.key === consoleKey);
  return {
    options: detectEmulatorsForConsole(homedir(), consoleKey),
    suggestions: consoleDef?.suggestions ?? [],
  };
});

ipcMain.handle("emulator:scan", (_event, params: {
  consoleKey: string;
  emulatorOption: DetectedEmulatorOption;
  extraPaths: string[];
}): EmulatorScanResult => {
  const { consoleKey, emulatorOption, extraPaths } = params;
  console.error(`[scan] consoleKey=${consoleKey} extraPaths=${JSON.stringify(extraPaths)} emulatorRomDirs=${JSON.stringify(emulatorOption.romDirs)}`);

  const consoleDef = CONSOLES.find(c => c.key === consoleKey);
  if (!consoleDef) {
    console.error(`[scan] ERROR: unknown consoleKey '${consoleKey}'`);
    return { emulators: [], romDirs: [], roms: [] };
  }

  const romExtSet = new Set(consoleDef.systemKeys);
  const romDirs = [...new Set([...emulatorOption.romDirs, ...(extraPaths ?? [])].filter(Boolean))];
  console.error(`[scan] romExtSet=${JSON.stringify([...romExtSet])} romDirs=${JSON.stringify(romDirs)}`);

  const firstSys = SYSTEMS[consoleDef.systemKeys[0]];
  const defaultSaveExts = firstSys?.saveExts ?? DEFAULT_SAVE_EXTS;

  const roms: RomEntry[] = romDirs.flatMap(dir => {
    const allInDir = scanRomDir(dir);
    console.error(`[scan] dir='${dir}' → scanRomDir found ${allInDir.length} files total`);
    const filtered = allInDir.filter(p => romExtSet.has(extname(p).slice(1).toLowerCase()));
    console.error(`[scan] dir='${dir}' → after ext filter (${[...romExtSet].join(",")}) kept ${filtered.length}`);
    return filtered
      .map(romPath => {
        const romExt = extname(romPath).slice(1).toLowerCase();
        const base   = basename(romPath, extname(romPath));
        const system = SYSTEMS[romExt];
        const saveExts = system?.saveExts ?? defaultSaveExts;

        // When a ROM lives in a per-game subfolder (e.g. roms/GBA/GameName/game.gba)
        // RetroArch's "Sort saves/states by content directory" option mirrors that
        // subfolder name into saves/ and states/ WITHOUT the core name subfolder:
        //   saves/GameName/game.srm  or  states/GameName/game.state
        // We must check those paths in addition to the core-subfolder patterns.
        const romParentDir    = dirname(romPath);
        const contentSubfolder = romParentDir !== dir ? basename(romParentDir) : null;
        const saveRoot  = emulatorOption.coreFolderName ? dirname(emulatorOption.saveDir)  : emulatorOption.saveDir;

        // ── Save file lookup (single file) ────────────────────────────────────
        // Priority: content-dir path first, then legacy core-subfolder / flat root.
        // Target path: savesRoot/GameName/GameName.ext  (no core-name layer)
        const gameFolderName = contentSubfolder ?? base;
        let m = matchSaveFile(join(saveRoot, gameFolderName), base, saveExts);
        if (!m.exists) {
          // saves/mGBA/GameName/base.ext  (core + content-dir)
          const mCC = matchSaveFile(join(emulatorOption.saveDir, gameFolderName), base, saveExts);
          if (mCC.exists) m = mCC;
        }
        if (!m.exists) {
          // saves/mGBA/base.ext  (core only, legacy flat)
          const mFlat = matchSaveFile(emulatorOption.saveDir, base, saveExts);
          if (mFlat.exists) m = mFlat;
        }
        if (!m.exists && emulatorOption.coreFolderName) {
          // saves/base.ext  (legacy flat root)
          const mRoot = matchSaveFile(saveRoot, base, saveExts);
          if (mRoot.exists) m = mRoot;
        }
        // Always register the canonical target path (savesRoot/GameName/base.ext)
        // so the path is correct even before RetroArch creates the file.
        if (!m.exists) {
          m = { path: join(saveRoot, gameFolderName, `${base}.${saveExts[0]}`), exists: false };
        }

        // ── State folder lookup ────────────────────────────────────────────────
        // state_path stores the FOLDER (statesRoot/GameName/) because multiple
        // state slots coexist there. We check whether it already has any files.
        let sm: { path: string; exists: boolean } | undefined;
        if (emulatorOption.stateDir) {
          const stateRoot = emulatorOption.coreFolderName ? dirname(emulatorOption.stateDir) : emulatorOption.stateDir;
          const stateFolder = join(stateRoot, gameFolderName);
          const hasStateFiles = !!findLatestFileInDir(stateFolder);
          sm = { path: stateFolder, exists: hasStateFiles };
        }

        const launchCommand = emulatorOption.corePath
          ? `${emulatorOption.execPath} -L "${emulatorOption.corePath}" "${romPath}"`
          : `${emulatorOption.execPath} "${romPath}"`;
        return {
          name: base, romPath,
          savePath: m.path, saveExists: m.exists,
          statePath: sm?.path, stateExists: sm?.exists,
          launchCommand,
          consoleName: system?.name ?? consoleDef.label,
          coreName: emulatorOption.coreFolderName,
        };
      });
  });

  console.error(`[scan] total ROMs returning to renderer: ${roms.length}`);
  return {
    emulators: [{ type: "native" as const, label: emulatorOption.label,
      execPath: emulatorOption.execPath, saveDir: emulatorOption.saveDir,
      coresDir: "", romDirs: emulatorOption.romDirs }],
    romDirs,
    roms,
  };
});

// Create an empty save file (+ parent dirs) if it doesn't already exist
ipcMain.handle("files:ensure-save", (_event, savePath: string): { created: boolean } => {
  try {
    if (existsSync(savePath)) return { created: false };
    mkdirSync(dirname(savePath), { recursive: true });
    writeFileSync(savePath, Buffer.alloc(0));
    return { created: true };
  } catch { return { created: false }; }
});

// Get the last modified time of a save file
ipcMain.handle("files:get-save-time", (_event, savePath: string): string | null => {
  try {
    if (!existsSync(savePath)) return null;
    const stats = statSync(savePath);
    return stats.mtime.toISOString().slice(0, 19);
  } catch { return null; }
});

ipcMain.handle("dialog:openFolder", async () => {
  const result = await dialog.showOpenDialog(mainWindow!, { properties: ["openDirectory"] });
  return result.canceled ? null : result.filePaths[0];
});

// TCP probe — resolves true if a TCP connection to ip:port succeeds within 2 s
ipcMain.handle("device:probe", (_event, ip: string, port: number): Promise<boolean> => {
  return new Promise((resolve) => {
    const net = require("net");
    const socket = new net.Socket();
    let settled = false;
    const finish = (result: boolean) => {
      if (settled) return;
      settled = true;
      socket.destroy();
      resolve(result);
    };
    socket.setTimeout(2000);
    socket.connect(port, ip, () => finish(true));
    socket.on("error", () => finish(false));
    socket.on("timeout", () => finish(false));
  });
});

// ── server config helper ──────────────────────────────────────────────────────

function loadServerCfg(): { host: string; port: number; authHeaders: Record<string, string> } {
  let cfg: Record<string, any> = {};
  if (existsSync(CONFIG_PATH)) {
    cfg = parseTOML(readFileSync(CONFIG_PATH, "utf-8")) as Record<string, any>;
  }
  const host = (cfg.server_host as string) || "localhost";
  const port = Number(cfg.server_port) || 8765;
  const pin  = (cfg.server_pin as string) || "";
  const deviceId   = (cfg.device_id as string) || "";
  const deviceName = (cfg.device_name as string) || "";
  const authHeaders: Record<string, string> = {
    "Authorization": `Bearer ${pin}`,
    "X-Device-ID": deviceId,
    "X-Device-Name": deviceName,
  };
  return { host, port, authHeaders };
}

// ── file utils ────────────────────────────────────────────────────────────────

function findLatestFileInDir(dirPath: string): { path: string; time: string } | null {
  try {
    if (!existsSync(dirPath)) return null;
    let latestMs = 0;
    let latest: { path: string; time: string } | null = null;
    for (const e of readdirSync(dirPath, { withFileTypes: true })) {
      if (!e.isFile()) continue;
      try {
        const fullPath = join(dirPath, e.name);
        const ms = statSync(fullPath).mtimeMs;
        if (ms > latestMs) {
          latestMs = ms;
          latest = { path: fullPath, time: new Date(ms).toISOString().slice(0, 19) };
        }
      } catch {}
    }
    return latest;
  } catch { return null; }
}

ipcMain.handle("files:get-latest-in-folder", (_event, dirPath: string) =>
  findLatestFileInDir(dirPath)
);

ipcMain.handle("files:move-to-subfolder", (
  _event,
  { romPath, subfolderName, newSavePath, newStateFolder }: {
    romPath: string;
    subfolderName: string;
    newSavePath: string;     // canonical target: savesRoot/GameName/base.ext
    newStateFolder: string;  // canonical target folder: statesRoot/GameName/
  }
): { ok: boolean; newRomPath: string; newSavePath: string; newStateFolder: string; error?: string } => {
  try {
    // ── ROM ───────────────────────────────────────────────────────────────────
    const newRomDir = join(dirname(romPath), subfolderName);
    mkdirSync(newRomDir, { recursive: true });
    const newRomPath = join(newRomDir, basename(romPath));
    renameSync(romPath, newRomPath);

    // ── Save file ─────────────────────────────────────────────────────────────
    // Target: savesRoot/GameName/base.ext.
    // If not already there, search common legacy locations and migrate.
    if (newSavePath && !existsSync(newSavePath)) {
      mkdirSync(dirname(newSavePath), { recursive: true });
      const base     = basename(newSavePath, extname(newSavePath));
      const ext      = extname(newSavePath).slice(1);
      // savesRoot = two levels up from the file (…/GameName/base.ext → …/)
      const savesRoot = dirname(dirname(newSavePath));
      // Check legacy patterns: flat root, then any immediate subdir (core folders)
      const flatLegacy = join(savesRoot, `${base}.${ext}`);
      if (existsSync(flatLegacy)) {
        renameSync(flatLegacy, newSavePath);
      } else {
        try {
          for (const e of readdirSync(savesRoot, { withFileTypes: true })) {
            if (!e.isDirectory()) continue;
            const candidate = join(savesRoot, e.name, `${base}.${ext}`);
            if (existsSync(candidate)) { renameSync(candidate, newSavePath); break; }
          }
        } catch {}
      }
    }

    // ── State folder ──────────────────────────────────────────────────────────
    // Target: statesRoot/GameName/ (folder, not a file).
    // Create it and migrate any existing state files from legacy locations.
    if (newStateFolder) {
      mkdirSync(newStateFolder, { recursive: true });
      const base        = basename(newStateFolder);  // = subfolderName = game base name
      const statesRoot  = dirname(newStateFolder);
      const stateExts   = ["state", "state.auto", "state1", "state2", "state3", "state4", "state5"];
      // Migrate flat root files: statesRoot/base.stateN
      for (const ext of stateExts) {
        const src = join(statesRoot, `${base}.${ext}`);
        if (existsSync(src)) renameSync(src, join(newStateFolder, `${base}.${ext}`));
      }
      // Migrate from any core-subfolder: statesRoot/mGBA/base.stateN
      try {
        for (const e of readdirSync(statesRoot, { withFileTypes: true })) {
          if (!e.isDirectory() || e.name === base) continue;
          for (const ext of stateExts) {
            const src = join(statesRoot, e.name, `${base}.${ext}`);
            if (existsSync(src)) renameSync(src, join(newStateFolder, `${base}.${ext}`));
          }
        }
      } catch {}
    }

    return { ok: true, newRomPath, newSavePath, newStateFolder };
  } catch (e: any) {
    return { ok: false, newRomPath: romPath, newSavePath, newStateFolder, error: e.message };
  }
});

// ── save sync ─────────────────────────────────────────────────────────────────

ipcMain.handle("save:push", async (_event, slug: string, savePath: string): Promise<{ ok: boolean; error?: string }> => {
  try {
    if (!existsSync(savePath)) return { ok: false, error: "Save file not found" };
    const { host, port, authHeaders } = loadServerCfg();
    const data = readFileSync(savePath);
    const res = await fetch(`http://${host}:${port}/games/${slug}/save`, {
      method: "POST",
      headers: { ...authHeaders, "Content-Type": "application/octet-stream" },
      body: data,
      signal: AbortSignal.timeout(30000),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      return { ok: false, error: (body as any).detail ?? res.statusText };
    }
    return { ok: true };
  } catch (e: any) {
    return { ok: false, error: e.message || "Push failed" };
  }
});

ipcMain.handle("save:pull", async (_event, slug: string, savePath: string): Promise<{ ok: boolean; pulled: boolean; error?: string }> => {
  try {
    const { host, port, authHeaders } = loadServerCfg();
    const res = await fetch(`http://${host}:${port}/games/${slug}/save`, {
      headers: authHeaders,
      signal: AbortSignal.timeout(30000),
    });
    if (res.status === 204) return { ok: true, pulled: false };
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      return { ok: false, pulled: false, error: (body as any).detail ?? res.statusText };
    }
    const buf = Buffer.from(await res.arrayBuffer());
    if (existsSync(savePath)) {
      writeFileSync(`${savePath}.bak`, readFileSync(savePath));
    }
    mkdirSync(dirname(savePath), { recursive: true });
    writeFileSync(savePath, buf);
    return { ok: true, pulled: true };
  } catch (e: any) {
    return { ok: false, pulled: false, error: e.message || "Pull failed" };
  }
});

// ── state sync ────────────────────────────────────────────────────────────────

ipcMain.handle("state:push", async (_event, slug: string, statePath: string): Promise<{ ok: boolean; error?: string }> => {
  try {
    // statePath is the state FOLDER (statesRoot/GameName/); find the newest file inside it
    const latest = findLatestFileInDir(statePath);
    if (!latest) return { ok: false, error: "No state files found in folder" };
    const { host, port, authHeaders } = loadServerCfg();
    const data = readFileSync(latest.path);
    const res = await fetch(`http://${host}:${port}/games/${slug}/state`, {
      method: "POST",
      headers: { ...authHeaders, "Content-Type": "application/octet-stream" },
      body: data,
      signal: AbortSignal.timeout(30000),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      return { ok: false, error: (body as any).detail ?? res.statusText };
    }
    return { ok: true };
  } catch (e: any) {
    return { ok: false, error: e.message || "Push failed" };
  }
});

ipcMain.handle("state:pull", async (_event, slug: string, statePath: string): Promise<{ ok: boolean; pulled: boolean; error?: string }> => {
  try {
    const { host, port, authHeaders } = loadServerCfg();
    const res = await fetch(`http://${host}:${port}/games/${slug}/state`, {
      headers: authHeaders,
      signal: AbortSignal.timeout(30000),
    });
    if (res.status === 204) return { ok: true, pulled: false };
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      return { ok: false, pulled: false, error: (body as any).detail ?? res.statusText };
    }
    const buf = Buffer.from(await res.arrayBuffer());
    // statePath is the state FOLDER; write the pulled state as GameName.state inside it.
    // Back up the current latest file in the folder first (if any).
    mkdirSync(statePath, { recursive: true });
    const existing = findLatestFileInDir(statePath);
    if (existing) {
      writeFileSync(`${existing.path}.bak`, readFileSync(existing.path));
    }
    const destFile = join(statePath, `${basename(statePath)}.state`);
    writeFileSync(destFile, buf);
    return { ok: true, pulled: true };
  } catch (e: any) {
    return { ok: false, pulled: false, error: e.message || "Pull failed" };
  }
});

// ── rom push ──────────────────────────────────────────────────────────────────

ipcMain.handle(
  "rom:push",
  async (_event, slug: string, toDeviceId: string, consoleName: string): Promise<{ ok: boolean; targetOnline?: boolean; error?: string }> => {
    try {
      // Read server config from TOML
      let cfg: Record<string, any> = {};
      if (existsSync(CONFIG_PATH)) {
        cfg = parseTOML(readFileSync(CONFIG_PATH, "utf-8")) as Record<string, any>;
      }
      const host = (cfg.server_host as string) || "localhost";
      const port = Number(cfg.server_port) || 8765;
      const pin  = (cfg.server_pin as string) || "";
      const deviceId   = (cfg.device_id as string) || "";
      const deviceName = (cfg.device_name as string) || "";
      const authHeaders: Record<string, string> = {
        "Authorization": `Bearer ${pin}`,
        "X-Device-ID": deviceId,
        "X-Device-Name": deviceName,
      };

      // 1. Get local game device config to find rom_path
      const gdRes = await fetch(`http://${host}:${port}/games/${slug}/device`, { headers: authHeaders, signal: AbortSignal.timeout(5000) });
      if (!gdRes.ok) return { ok: false, error: "This game is not configured on this device" };
      const gd = await gdRes.json() as any;
      if (!gd.rom_path) return { ok: false, error: "No ROM path configured for this game" };
      if (!existsSync(gd.rom_path)) return { ok: false, error: `ROM file not found: ${gd.rom_path}` };

      // 2. Get target device consoles to find its ROM folder for this console
      const consolesRes = await fetch(`http://${host}:${port}/devices/${toDeviceId}/consoles`, { headers: authHeaders, signal: AbortSignal.timeout(5000) });
      if (!consolesRes.ok) return { ok: false, error: "Could not read target device configuration" };
      const consoles = await consolesRes.json() as Array<{ console_name: string; device_game_folder: string }>;

      const match = consoles.find(c => c.console_name === consoleName);
      if (!match?.device_game_folder) {
        return { ok: false, error: `${consoleName} is not configured on the target device yet` };
      }

      const romFilename = basename(gd.rom_path);
      const destinationPath = join(match.device_game_folder, romFilename);
      const fileSize = statSync(gd.rom_path).size;

      // 3. Stream ROM file to server via http.request (fetch can't stream a local file reliably)
      const result = await new Promise<any>((resolve, reject) => {
        const req = httpRequest(
          {
            method: "POST",
            host,
            port,
            path: `/games/${slug}/rom-transfer`,
            headers: {
              ...authHeaders,
              "Content-Type": "application/octet-stream",
              "Content-Length": fileSize,
              "X-To-Device-ID": toDeviceId,
              "X-Destination-Path": destinationPath,
              "X-Filename": romFilename,
            },
          },
          (res) => {
            let body = "";
            res.on("data", (chunk: Buffer) => { body += chunk.toString(); });
            res.on("end", () => {
              if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) {
                try { resolve(JSON.parse(body)); } catch { resolve({}); }
              } else {
                try {
                  const msg = JSON.parse(body);
                  reject(new Error(msg.detail || `Server error ${res.statusCode}`));
                } catch {
                  reject(new Error(`Server error ${res.statusCode}`));
                }
              }
            });
          }
        );
        req.on("error", reject);
        createReadStream(gd.rom_path).pipe(req);
      });

      return { ok: true, targetOnline: result.target_online };
    } catch (e: any) {
      return { ok: false, error: e.message || "Push failed" };
    }
  }
);

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
  if (serverStartedByApp) {
    killServerByPid();
    void killOrphanServers();
  }
  if (process.platform !== "darwin") app.quit();
});
