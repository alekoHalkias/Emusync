"use strict";
const electron = require("electron");
const child_process = require("child_process");
const fs = require("fs");
const http = require("http");
const path = require("path");
const os = require("os");
const smolToml = require("smol-toml");
const CONFIG_PATH = path.join(os.homedir(), ".emusync", "emusync.toml");
const SCRIPT = process.env.EMUSYNC_SCRIPT ?? path.join(__dirname, "../../../emusync.py");
const PYTHON = process.env.EMUSYNC_PYTHON ?? (() => {
  const venv = path.join(path.dirname(SCRIPT), ".venv", "bin", "python");
  return require("fs").existsSync(venv) ? venv : "python3";
})();
let serverProcess = null;
let serverStartedByApp = false;
let gameProcess = null;
let syncDaemonProcess = null;
let syncDaemonRestartTimer = null;
let mainWindow = null;
function startSyncDaemon() {
  if (syncDaemonProcess) return;
  if (fs.existsSync(CONFIG_PATH)) {
    try {
      const cfg = smolToml.parse(fs.readFileSync(CONFIG_PATH, "utf-8"));
      if (cfg.is_server) return;
    } catch {
      return;
    }
  } else {
    return;
  }
  try {
    const proc = child_process.spawn(PYTHON, [SCRIPT, "sync-daemon"], {
      stdio: "ignore",
      env: { ...process.env, PYTHONUNBUFFERED: "1" }
    });
    syncDaemonProcess = proc;
    proc.on("exit", () => {
      syncDaemonProcess = null;
      syncDaemonRestartTimer = setTimeout(() => {
        syncDaemonRestartTimer = null;
        startSyncDaemon();
      }, 1e4);
    });
    proc.on("error", (err) => {
      console.error("Sync daemon error:", err);
      syncDaemonProcess = null;
    });
  } catch (err) {
    console.error("Failed to start sync daemon:", err);
  }
}
function stopSyncDaemon() {
  if (syncDaemonRestartTimer) {
    clearTimeout(syncDaemonRestartTimer);
    syncDaemonRestartTimer = null;
  }
  if (syncDaemonProcess) {
    syncDaemonProcess.kill("SIGKILL");
    syncDaemonProcess = null;
  }
}
function createWindow() {
  mainWindow = new electron.BrowserWindow({
    width: 900,
    height: 650,
    minWidth: 700,
    minHeight: 500,
    title: "EmuSync",
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "../preload/preload.js"),
      contextIsolation: true,
      nodeIntegration: false
    }
  });
  if (process.env.NODE_ENV === "development") {
    mainWindow.loadURL("http://localhost:5173");
  } else {
    mainWindow.loadFile(path.join(__dirname, "../renderer/index.html"));
  }
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    electron.shell.openExternal(url);
    return { action: "deny" };
  });
}
electron.ipcMain.handle("config:load", () => {
  if (!fs.existsSync(CONFIG_PATH)) return null;
  try {
    return smolToml.parse(fs.readFileSync(CONFIG_PATH, "utf-8"));
  } catch {
    return null;
  }
});
electron.ipcMain.handle("config:save", (_event, data) => {
  fs.mkdirSync(path.dirname(CONFIG_PATH), { recursive: true });
  fs.writeFileSync(CONFIG_PATH, smolToml.stringify(data));
  return true;
});
electron.ipcMain.handle("config:exists", () => fs.existsSync(CONFIG_PATH));
electron.ipcMain.handle("config:getRecentFolders", (_event, consoleKey) => {
  if (!fs.existsSync(CONFIG_PATH)) return [];
  try {
    const data = smolToml.parse(fs.readFileSync(CONFIG_PATH, "utf-8"));
    const recentFolders = data.recent_import_folders || {};
    return recentFolders[consoleKey] || [];
  } catch {
    return [];
  }
});
electron.ipcMain.handle("config:addRecentFolder", (_event, consoleKey, folderPath) => {
  if (!fs.existsSync(CONFIG_PATH)) return;
  try {
    const data = smolToml.parse(fs.readFileSync(CONFIG_PATH, "utf-8"));
    if (!data.recent_import_folders) {
      data.recent_import_folders = {};
    }
    const recentFolders = data.recent_import_folders;
    if (!recentFolders[consoleKey]) {
      recentFolders[consoleKey] = [];
    }
    const folders = recentFolders[consoleKey];
    const index = folders.indexOf(folderPath);
    if (index !== -1) {
      folders.splice(index, 1);
    }
    folders.unshift(folderPath);
    folders.splice(10);
    fs.writeFileSync(CONFIG_PATH, smolToml.stringify(data));
  } catch {
  }
});
function startServerProcess() {
  if (serverProcess) return Promise.resolve({ ok: true });
  return new Promise((resolve) => {
    let resolved = false;
    const proc = child_process.spawn(PYTHON, [SCRIPT, "server", "start"], {
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, PYTHONUNBUFFERED: "1" }
    });
    serverProcess = proc;
    proc.stdout?.on("data", (chunk) => {
      const line = chunk.toString();
      if (!resolved && line.includes("EmuSync server ready")) {
        resolved = true;
        serverStartedByApp = true;
        resolve({ ok: true });
      }
    });
    proc.on("error", (err) => {
      serverProcess = null;
      if (!resolved) {
        resolved = true;
        resolve({ ok: false });
      }
      console.error("Server process error:", err);
    });
    proc.on("exit", () => {
      serverProcess = null;
    });
    setTimeout(() => {
      if (!resolved) {
        resolved = true;
        resolve({ ok: true });
      }
    }, 5e3);
  });
}
electron.ipcMain.handle("server:start", () => startServerProcess());
electron.ipcMain.handle("daemon:start", () => {
  startSyncDaemon();
});
electron.ipcMain.handle("daemon:stop", () => {
  stopSyncDaemon();
});
function killServerByPid() {
  const pidFile = path.join(os.homedir(), ".emusync", ".server_pid");
  try {
    if (fs.existsSync(pidFile)) {
      const pid = parseInt(fs.readFileSync(pidFile, "utf-8").trim(), 10);
      if (pid) try {
        process.kill(pid, "SIGKILL");
      } catch {
      }
      fs.unlinkSync(pidFile);
    }
  } catch {
  }
  try {
    fs.unlinkSync(path.join(os.homedir(), ".emusync", ".server_token"));
  } catch {
  }
}
function killOrphanServers() {
  return new Promise((resolve) => {
    const proc = child_process.spawn("pkill", ["-9", "-f", "emusync.py server start"], { stdio: "ignore" });
    proc.on("exit", resolve);
    proc.on("error", resolve);
    setTimeout(resolve, 1e3);
  });
}
electron.ipcMain.handle("server:stop", async () => {
  if (serverProcess) {
    serverProcess.kill("SIGKILL");
    serverProcess = null;
  }
  killServerByPid();
  await killOrphanServers();
  serverStartedByApp = false;
  return true;
});
electron.ipcMain.handle("server:token", () => null);
electron.ipcMain.handle("server:discover", () => {
  return new Promise((resolve) => {
    const proc = child_process.spawn(PYTHON, [SCRIPT, "server", "discover-json"], {
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, PYTHONUNBUFFERED: "1" }
    });
    let output = "";
    proc.stdout?.on("data", (chunk) => {
      output += chunk.toString();
    });
    proc.on("exit", () => {
      try {
        resolve(JSON.parse(output));
      } catch {
        resolve([]);
      }
    });
    proc.on("error", () => resolve([]));
  });
});
electron.ipcMain.handle("server:local-ip", () => {
  const nets = os.networkInterfaces();
  for (const name of Object.keys(nets)) {
    for (const iface of nets[name] ?? []) {
      if (iface.family === "IPv4" && !iface.internal) return iface.address;
    }
  }
  return null;
});
electron.ipcMain.handle("server:change-pin", async (_event, pin) => {
  if (serverProcess) {
    serverProcess.kill("SIGKILL");
    serverProcess = null;
  }
  killServerByPid();
  await killOrphanServers();
  const raw = fs.existsSync(CONFIG_PATH) ? smolToml.parse(fs.readFileSync(CONFIG_PATH, "utf-8")) : {};
  if (pin) {
    raw.server_pin = pin;
  } else {
    delete raw.server_pin;
  }
  fs.writeFileSync(CONFIG_PATH, smolToml.stringify(raw));
  return startServerProcess();
});
electron.ipcMain.handle("launcher:path", () => path.join(path.dirname(SCRIPT), "emusync"));
electron.ipcMain.handle("dialog:openFile", async (_event, options) => {
  const result = await electron.dialog.showOpenDialog(mainWindow, options);
  return result.canceled ? null : result.filePaths[0];
});
electron.ipcMain.handle("game:launch", (_event, slug, command) => {
  if (gameProcess) return { ok: false };
  const args = (command.match(/(?:[^\s"']+|"[^"]*"|'[^']*')+/g) ?? []).map((a) => /^["']/.test(a) ? a.slice(1, -1) : a);
  const proc = child_process.spawn(PYTHON, [SCRIPT, "run", "--game", slug, "--", ...args], {
    stdio: "ignore",
    detached: true,
    env: { ...process.env, DISPLAY: process.env.DISPLAY || ":0", WAYLAND_DISPLAY: process.env.WAYLAND_DISPLAY || "wayland-0" }
  });
  gameProcess = proc;
  proc.on("exit", () => {
    gameProcess = null;
    mainWindow?.webContents.send("game:exited");
  });
  proc.unref();
  return { ok: true };
});
electron.ipcMain.handle("game:stop", () => {
  if (gameProcess?.pid) {
    try {
      process.kill(-gameProcess.pid, "SIGTERM");
    } catch {
      gameProcess.kill("SIGTERM");
    }
  }
  return { ok: true };
});
electron.ipcMain.handle("game:isRunning", () => gameProcess !== null);
electron.ipcMain.handle("game:stop-external", () => {
  const gamePidFile = path.join(os.homedir(), ".emusync", ".game_pid");
  try {
    if (fs.existsSync(gamePidFile)) {
      const lines = fs.readFileSync(gamePidFile, "utf-8").trim().split("\n");
      const emusyncPid = parseInt(lines[0], 10);
      const childPid = lines[1] ? parseInt(lines[1], 10) : NaN;
      if (childPid) try {
        process.kill(childPid, "SIGKILL");
      } catch {
      }
      if (emusyncPid) try {
        process.kill(emusyncPid, "SIGTERM");
      } catch {
      }
    }
  } catch {
  }
  return { ok: true };
});
electron.ipcMain.handle("game:hasPidFile", () => {
  const gamePidFile = path.join(os.homedir(), ".emusync", ".game_pid");
  if (!fs.existsSync(gamePidFile)) return false;
  try {
    const pid = parseInt(fs.readFileSync(gamePidFile, "utf-8").trim().split("\n")[0], 10);
    if (!pid) return false;
    try {
      process.kill(pid, 0);
    } catch {
      return false;
    }
    try {
      const cmdline = fs.readFileSync(`/proc/${pid}/cmdline`, "utf-8");
      return cmdline.includes("emusync") || cmdline.includes("python");
    } catch {
      return true;
    }
  } catch {
    return false;
  }
});
const ROM_EXTENSIONS = /* @__PURE__ */ new Set([
  "sfc",
  "smc",
  // SNES
  "gb",
  "gbc",
  // Game Boy / Color
  "gba",
  // Game Boy Advance
  "nes",
  "fds",
  // NES
  "n64",
  "z64",
  "v64",
  // Nintendo 64
  "nds",
  // Nintendo DS
  "md",
  "smd",
  "gen",
  // Sega Genesis / Mega Drive
  "sms",
  "gg",
  // Sega Master System / Game Gear
  "32x",
  // Sega 32X
  "pce",
  // PC Engine
  "ws",
  "wsc",
  // WonderSwan
  "ngp",
  "ngc",
  // Neo Geo Pocket
  "a26",
  "a52",
  "a78",
  // Atari
  "lnx",
  // Atari Lynx
  "iso",
  "cue",
  "bin",
  "chd",
  "pbp"
  // Disc-based (PSX, Dreamcast, PSP…)
]);
const DEFAULT_SAVE_EXTS = ["srm", "sav", "save"];
const SYSTEMS = {
  // ── Game Boy family ────────────────────────────────────────────────────────
  gba: {
    name: "Game Boy Advance",
    saveExts: ["sav", "srm"],
    cores: [
      { libName: "mgba_libretro", folderName: "mGBA" },
      { libName: "vba_next_libretro", folderName: "VBA Next" },
      { libName: "vbam_libretro", folderName: "VBA-M" }
    ]
  },
  gb: {
    name: "Game Boy",
    saveExts: ["sav", "srm"],
    cores: [
      { libName: "gambatte_libretro", folderName: "Gambatte" },
      { libName: "mgba_libretro", folderName: "mGBA" },
      { libName: "gearboy_libretro", folderName: "Gearboy" }
    ]
  },
  gbc: {
    name: "Game Boy Color",
    saveExts: ["sav", "srm"],
    cores: [
      { libName: "gambatte_libretro", folderName: "Gambatte" },
      { libName: "mgba_libretro", folderName: "mGBA" },
      { libName: "gearboy_libretro", folderName: "Gearboy" }
    ]
  },
  // ── SNES ──────────────────────────────────────────────────────────────────
  sfc: {
    name: "SNES",
    saveExts: ["srm", "sav"],
    cores: [
      { libName: "snes9x_libretro", folderName: "Snes9x" },
      { libName: "bsnes_libretro", folderName: "bsnes" },
      { libName: "snes9x2010_libretro", folderName: "Snes9x 2010" }
    ]
  },
  smc: {
    name: "SNES",
    saveExts: ["srm", "sav"],
    cores: [
      { libName: "snes9x_libretro", folderName: "Snes9x" },
      { libName: "bsnes_libretro", folderName: "bsnes" },
      { libName: "snes9x2010_libretro", folderName: "Snes9x 2010" }
    ]
  },
  // ── NES ───────────────────────────────────────────────────────────────────
  nes: {
    name: "NES",
    saveExts: ["sav", "srm"],
    cores: [
      { libName: "nestopia_libretro", folderName: "Nestopia UE" },
      { libName: "fceumm_libretro", folderName: "FCEUmm" },
      { libName: "mesen_libretro", folderName: "Mesen" }
    ]
  },
  fds: {
    name: "Famicom Disk System",
    saveExts: ["sav", "srm"],
    cores: [
      { libName: "nestopia_libretro", folderName: "Nestopia UE" },
      { libName: "fceumm_libretro", folderName: "FCEUmm" }
    ]
  },
  // ── Nintendo 64 ───────────────────────────────────────────────────────────
  n64: {
    name: "Nintendo 64",
    saveExts: ["srm", "sav", "eep", "mpk"],
    cores: [
      { libName: "mupen64plus_next_libretro", folderName: "Mupen64Plus-Next" },
      { libName: "parallel_n64_libretro", folderName: "ParaLLEl N64" }
    ]
  },
  z64: {
    name: "Nintendo 64",
    saveExts: ["srm", "sav", "eep", "mpk"],
    cores: [
      { libName: "mupen64plus_next_libretro", folderName: "Mupen64Plus-Next" },
      { libName: "parallel_n64_libretro", folderName: "ParaLLEl N64" }
    ]
  },
  v64: {
    name: "Nintendo 64",
    saveExts: ["srm", "sav", "eep", "mpk"],
    cores: [
      { libName: "mupen64plus_next_libretro", folderName: "Mupen64Plus-Next" },
      { libName: "parallel_n64_libretro", folderName: "ParaLLEl N64" }
    ]
  },
  // ── Nintendo DS ───────────────────────────────────────────────────────────
  nds: {
    name: "Nintendo DS",
    saveExts: ["sav", "dsv", "srm"],
    cores: [
      { libName: "melonds_libretro", folderName: "melonDS" },
      { libName: "desmume_libretro", folderName: "DeSmuME" },
      { libName: "desmume2015_libretro", folderName: "DeSmuME 2015" }
    ]
  },
  // ── Sega Genesis / Mega Drive ─────────────────────────────────────────────
  md: {
    name: "Sega Genesis",
    saveExts: ["srm", "sav"],
    cores: [
      { libName: "genesis_plus_gx_libretro", folderName: "Genesis Plus GX" },
      { libName: "picodrive_libretro", folderName: "PicoDrive" }
    ]
  },
  smd: {
    name: "Sega Genesis",
    saveExts: ["srm", "sav"],
    cores: [
      { libName: "genesis_plus_gx_libretro", folderName: "Genesis Plus GX" },
      { libName: "picodrive_libretro", folderName: "PicoDrive" }
    ]
  },
  gen: {
    name: "Sega Genesis",
    saveExts: ["srm", "sav"],
    cores: [
      { libName: "genesis_plus_gx_libretro", folderName: "Genesis Plus GX" },
      { libName: "picodrive_libretro", folderName: "PicoDrive" }
    ]
  },
  // ── Sega Master System / Game Gear ────────────────────────────────────────
  sms: {
    name: "Sega Master System",
    saveExts: ["srm", "sav"],
    cores: [
      { libName: "genesis_plus_gx_libretro", folderName: "Genesis Plus GX" },
      { libName: "picodrive_libretro", folderName: "PicoDrive" }
    ]
  },
  gg: {
    name: "Game Gear",
    saveExts: ["srm", "sav"],
    cores: [
      { libName: "genesis_plus_gx_libretro", folderName: "Genesis Plus GX" }
    ]
  },
  // ── PC Engine ─────────────────────────────────────────────────────────────
  pce: {
    name: "PC Engine",
    saveExts: ["srm", "sav"],
    cores: [
      { libName: "mednafen_pce_libretro", folderName: "Beetle PCE" },
      { libName: "mednafen_pce_fast_libretro", folderName: "Beetle PCE Fast" }
    ]
  },
  // ── Disc-based (PSX / Dreamcast / PSP) ───────────────────────────────────
  iso: {
    name: "Disc",
    saveExts: ["mcr", "srm", "sav"],
    cores: [
      { libName: "pcsx_rearmed_libretro", folderName: "PCSX-ReARMed" },
      { libName: "mednafen_psx_libretro", folderName: "Beetle PSX" },
      { libName: "mednafen_psx_hw_libretro", folderName: "Beetle PSX HW" },
      { libName: "flycast_libretro", folderName: "Flycast" },
      { libName: "ppsspp_libretro", folderName: "PPSSPP" }
    ]
  },
  bin: {
    name: "Disc",
    saveExts: ["mcr", "srm", "sav"],
    cores: [
      { libName: "pcsx_rearmed_libretro", folderName: "PCSX-ReARMed" },
      { libName: "mednafen_psx_libretro", folderName: "Beetle PSX" }
    ]
  },
  cue: {
    name: "Disc",
    saveExts: ["mcr", "srm", "sav"],
    cores: [
      { libName: "pcsx_rearmed_libretro", folderName: "PCSX-ReARMed" },
      { libName: "mednafen_psx_libretro", folderName: "Beetle PSX" }
    ]
  },
  chd: {
    name: "Disc (CHD)",
    saveExts: ["mcr", "srm", "sav"],
    cores: [
      { libName: "pcsx_rearmed_libretro", folderName: "PCSX-ReARMed" },
      { libName: "mednafen_psx_libretro", folderName: "Beetle PSX" },
      { libName: "flycast_libretro", folderName: "Flycast" }
    ]
  },
  pbp: {
    name: "PSP / PS1",
    saveExts: ["srm", "sav", "mcr"],
    cores: [
      { libName: "ppsspp_libretro", folderName: "PPSSPP" },
      { libName: "pcsx_rearmed_libretro", folderName: "PCSX-ReARMed" }
    ]
  }
};
function parseRetroArchCfg(cfgPath, home) {
  const out = {};
  if (!fs.existsSync(cfgPath)) return out;
  const expandHome = (v) => v.startsWith("~/") ? path.join(home, v.slice(2)) : v === "~" ? home : v;
  for (const line of fs.readFileSync(cfgPath, "utf-8").split("\n")) {
    const m = line.match(/^\s*(\w+)\s*=\s*"?([^"#\r\n]*)"?\s*$/);
    if (m) out[m[1].trim()] = expandHome(m[2].trim());
  }
  return out;
}
function detectRetroArch(home) {
  const infos = [];
  const nativeBins = ["/usr/bin/retroarch", "/usr/local/bin/retroarch", path.join(home, ".local/bin/retroarch")];
  const nativeCfg = path.join(home, ".config/retroarch/retroarch.cfg");
  for (const bin of nativeBins) {
    if (fs.existsSync(bin)) {
      const cfg = parseRetroArchCfg(nativeCfg, home);
      const romDir = cfg.rgui_browser_directory && cfg.rgui_browser_directory !== "default" ? cfg.rgui_browser_directory : "";
      infos.push({
        type: "native",
        label: "RetroArch",
        execPath: bin,
        saveDir: cfg.savefile_directory || path.join(home, ".config/retroarch/saves"),
        statesDir: cfg.savestate_directory || path.join(home, ".config/retroarch/states"),
        coresDir: cfg.libretro_directory || path.join(home, ".config/retroarch/cores"),
        romDirs: [romDir].filter(Boolean)
      });
      break;
    }
  }
  try {
    const list = child_process.execSync("flatpak list --app --columns=application 2>/dev/null", { timeout: 5e3 }).toString();
    if (list.includes("org.libretro.RetroArch")) {
      const flatCfg = path.join(home, ".var/app/org.libretro.RetroArch/config/retroarch/retroarch.cfg");
      const cfg = parseRetroArchCfg(flatCfg, home);
      const flatRomDir = cfg.rgui_browser_directory && cfg.rgui_browser_directory !== "default" ? cfg.rgui_browser_directory : "";
      infos.push({
        type: "flatpak",
        label: "RetroArch (Flatpak)",
        execPath: "flatpak run org.libretro.RetroArch",
        saveDir: cfg.savefile_directory || path.join(home, ".var/app/org.libretro.RetroArch/config/retroarch/saves"),
        statesDir: cfg.savestate_directory || path.join(home, ".var/app/org.libretro.RetroArch/config/retroarch/states"),
        coresDir: cfg.libretro_directory || path.join(home, ".var/app/org.libretro.RetroArch/data/retroarch/cores"),
        romDirs: [flatRomDir].filter(Boolean)
      });
    }
  } catch {
  }
  return infos;
}
function findInstalledCore(coresDir, system) {
  for (const core of system.cores) {
    const soPath = path.join(coresDir, `${core.libName}.so`);
    if (fs.existsSync(soPath)) return { lib: soPath, folderName: core.folderName };
  }
  return null;
}
function scanRomDir(dir, depth = 0) {
  if (depth > 3) return [];
  try {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    const roms = [];
    for (const e of entries) {
      if (e.isFile() && ROM_EXTENSIONS.has(path.extname(e.name).slice(1).toLowerCase())) {
        roms.push(path.join(dir, e.name));
      } else if (e.isDirectory()) {
        roms.push(...scanRomDir(path.join(dir, e.name), depth + 1));
      }
    }
    return roms;
  } catch {
    return [];
  }
}
function matchSaveFile(saveDir, baseName, exts) {
  for (const ext of exts) {
    const p = path.join(saveDir, `${baseName}.${ext}`);
    if (fs.existsSync(p)) return { path: p, exists: true };
  }
  return { path: path.join(saveDir, `${baseName}.${exts[0]}`), exists: false };
}
const CONSOLES = [
  {
    key: "gba",
    label: "Game Boy Advance",
    systemKeys: ["gba"],
    standalones: [
      {
        id: "mgba",
        label: "mGBA",
        nativeBins: ["/usr/bin/mgba-qt", "/usr/bin/mgba", path.join(os.homedir(), ".local/bin/mgba-qt")],
        flatpakId: "io.mgba.mGBA",
        flatpakExec: "flatpak run io.mgba.mGBA",
        getDefaultSaveDir: (h) => path.join(h, ".local/share/mGBA/saves")
      }
    ],
    suggestions: ["RetroArch with mGBA core", "mGBA standalone"]
  },
  {
    key: "gb",
    label: "Game Boy / Game Boy Color",
    systemKeys: ["gb", "gbc"],
    standalones: [
      {
        id: "mgba",
        label: "mGBA",
        nativeBins: ["/usr/bin/mgba-qt", "/usr/bin/mgba"],
        flatpakId: "io.mgba.mGBA",
        flatpakExec: "flatpak run io.mgba.mGBA",
        getDefaultSaveDir: (h) => path.join(h, ".local/share/mGBA/saves")
      }
    ],
    suggestions: ["RetroArch with Gambatte or mGBA core", "mGBA standalone"]
  },
  {
    key: "snes",
    label: "Super Nintendo (SNES)",
    systemKeys: ["sfc", "smc"],
    standalones: [],
    suggestions: ["RetroArch with Snes9x core"]
  },
  {
    key: "nes",
    label: "NES / Famicom",
    systemKeys: ["nes", "fds"],
    standalones: [],
    suggestions: ["RetroArch with Nestopia UE or FCEUmm core"]
  },
  {
    key: "n64",
    label: "Nintendo 64",
    systemKeys: ["n64", "z64", "v64"],
    standalones: [],
    suggestions: ["RetroArch with Mupen64Plus-Next core"]
  },
  {
    key: "nds",
    label: "Nintendo DS",
    systemKeys: ["nds"],
    standalones: [],
    suggestions: ["RetroArch with melonDS or DeSmuME core"]
  },
  {
    key: "genesis",
    label: "Sega Genesis / Mega Drive",
    systemKeys: ["md", "smd", "gen"],
    standalones: [],
    suggestions: ["RetroArch with Genesis Plus GX core"]
  },
  {
    key: "sms",
    label: "Master System / Game Gear",
    systemKeys: ["sms", "gg"],
    standalones: [],
    suggestions: ["RetroArch with Genesis Plus GX core"]
  },
  {
    key: "pce",
    label: "PC Engine",
    systemKeys: ["pce"],
    standalones: [],
    suggestions: ["RetroArch with Beetle PCE core"]
  },
  {
    key: "psx",
    label: "PlayStation",
    systemKeys: ["iso", "bin", "cue", "chd", "pbp"],
    standalones: [],
    suggestions: ["RetroArch with PCSX-ReARMed or Beetle PSX core"]
  }
];
function detectEmulatorsForConsole(home, consoleKey) {
  const consoleDef = CONSOLES.find((c) => c.key === consoleKey);
  if (!consoleDef) return [];
  const options = [];
  for (const ra of detectRetroArch(home)) {
    const seenCores = /* @__PURE__ */ new Set();
    for (const sysKey of consoleDef.systemKeys) {
      const sys = SYSTEMS[sysKey];
      if (!sys) continue;
      const core = findInstalledCore(ra.coresDir, sys);
      if (!core || seenCores.has(core.lib)) continue;
      seenCores.add(core.lib);
      const saveDir = path.join(ra.saveDir, core.folderName);
      const stateDir = path.join(ra.statesDir, core.folderName);
      options.push({
        id: `${ra.type}-${core.folderName.toLowerCase().replace(/[^a-z0-9]/g, "-")}`,
        label: `${ra.label} · ${core.folderName}`,
        execPath: ra.execPath,
        saveDir,
        stateDir,
        corePath: core.lib,
        coreFolderName: core.folderName,
        romDirs: ra.romDirs
      });
    }
  }
  let flatpakList = null;
  const getFlatpakList = () => {
    if (flatpakList !== null) return flatpakList;
    try {
      flatpakList = child_process.execSync("flatpak list --app --columns=application 2>/dev/null", { timeout: 5e3 }).toString();
    } catch {
      flatpakList = "";
    }
    return flatpakList;
  };
  for (const s of consoleDef.standalones) {
    let found = false;
    for (const bin of s.nativeBins) {
      if (fs.existsSync(bin)) {
        options.push({
          id: `${s.id}-native`,
          label: s.label,
          execPath: bin,
          saveDir: s.getDefaultSaveDir(home),
          romDirs: []
        });
        found = true;
        break;
      }
    }
    if (!found && s.flatpakId && s.flatpakExec && getFlatpakList().includes(s.flatpakId)) {
      options.push({
        id: `${s.id}-flatpak`,
        label: `${s.label} (Flatpak)`,
        execPath: s.flatpakExec,
        saveDir: path.join(home, `.var/app/${s.flatpakId}/data/${s.id}/saves`),
        romDirs: []
      });
    }
  }
  return options;
}
electron.ipcMain.handle(
  "emulator:consoles",
  () => CONSOLES.map((c) => ({ key: c.key, label: c.label }))
);
electron.ipcMain.handle("emulator:detect", (_event, consoleKey) => {
  const consoleDef = CONSOLES.find((c) => c.key === consoleKey);
  return {
    options: detectEmulatorsForConsole(os.homedir(), consoleKey),
    suggestions: consoleDef?.suggestions ?? []
  };
});
electron.ipcMain.handle("emulator:scan", (_event, params) => {
  const { consoleKey, emulatorOption, extraPaths } = params;
  console.error(`[scan] consoleKey=${consoleKey} extraPaths=${JSON.stringify(extraPaths)} emulatorRomDirs=${JSON.stringify(emulatorOption.romDirs)}`);
  const consoleDef = CONSOLES.find((c) => c.key === consoleKey);
  if (!consoleDef) {
    console.error(`[scan] ERROR: unknown consoleKey '${consoleKey}'`);
    return { emulators: [], romDirs: [], roms: [] };
  }
  const romExtSet = new Set(consoleDef.systemKeys);
  const romDirs = [...new Set([...emulatorOption.romDirs, ...extraPaths ?? []].filter(Boolean))];
  console.error(`[scan] romExtSet=${JSON.stringify([...romExtSet])} romDirs=${JSON.stringify(romDirs)}`);
  const firstSys = SYSTEMS[consoleDef.systemKeys[0]];
  const defaultSaveExts = firstSys?.saveExts ?? DEFAULT_SAVE_EXTS;
  const roms = romDirs.flatMap((dir) => {
    const allInDir = scanRomDir(dir);
    console.error(`[scan] dir='${dir}' → scanRomDir found ${allInDir.length} files total`);
    const filtered = allInDir.filter((p) => romExtSet.has(path.extname(p).slice(1).toLowerCase()));
    console.error(`[scan] dir='${dir}' → after ext filter (${[...romExtSet].join(",")}) kept ${filtered.length}`);
    return filtered.map((romPath) => {
      const romExt = path.extname(romPath).slice(1).toLowerCase();
      const base = path.basename(romPath, path.extname(romPath));
      const system = SYSTEMS[romExt];
      const saveExts = system?.saveExts ?? defaultSaveExts;
      const romParentDir = path.dirname(romPath);
      const contentSubfolder = romParentDir !== dir ? path.basename(romParentDir) : null;
      const saveRoot = emulatorOption.coreFolderName ? path.dirname(emulatorOption.saveDir) : emulatorOption.saveDir;
      const gameFolderName = contentSubfolder ?? base;
      let m = matchSaveFile(path.join(saveRoot, gameFolderName), base, saveExts);
      if (!m.exists) {
        const mCC = matchSaveFile(path.join(emulatorOption.saveDir, gameFolderName), base, saveExts);
        if (mCC.exists) m = mCC;
      }
      if (!m.exists) {
        const mFlat = matchSaveFile(emulatorOption.saveDir, base, saveExts);
        if (mFlat.exists) m = mFlat;
      }
      if (!m.exists && emulatorOption.coreFolderName) {
        const mRoot = matchSaveFile(saveRoot, base, saveExts);
        if (mRoot.exists) m = mRoot;
      }
      if (!m.exists) {
        m = { path: path.join(saveRoot, gameFolderName, `${base}.${saveExts[0]}`), exists: false };
      }
      let sm;
      if (emulatorOption.stateDir) {
        const stateRoot = emulatorOption.coreFolderName ? path.dirname(emulatorOption.stateDir) : emulatorOption.stateDir;
        const stateFolder = path.join(stateRoot, gameFolderName);
        const hasStateFiles = !!findLatestFileInDir(stateFolder);
        sm = { path: stateFolder, exists: hasStateFiles };
      }
      const launchCommand = emulatorOption.corePath ? `${emulatorOption.execPath} -L "${emulatorOption.corePath}" "${romPath}"` : `${emulatorOption.execPath} "${romPath}"`;
      return {
        name: base,
        romPath,
        savePath: m.path,
        saveExists: m.exists,
        statePath: sm?.path,
        stateExists: sm?.exists,
        launchCommand,
        consoleName: system?.name ?? consoleDef.label,
        coreName: emulatorOption.coreFolderName
      };
    });
  });
  console.error(`[scan] total ROMs returning to renderer: ${roms.length}`);
  return {
    emulators: [{
      type: "native",
      label: emulatorOption.label,
      execPath: emulatorOption.execPath,
      saveDir: emulatorOption.saveDir,
      coresDir: "",
      romDirs: emulatorOption.romDirs
    }],
    romDirs,
    roms
  };
});
electron.ipcMain.handle("files:ensure-save", (_event, savePath) => {
  try {
    if (fs.existsSync(savePath)) return { created: false };
    fs.mkdirSync(path.dirname(savePath), { recursive: true });
    fs.writeFileSync(savePath, Buffer.alloc(0));
    return { created: true };
  } catch {
    return { created: false };
  }
});
electron.ipcMain.handle("files:get-save-time", (_event, savePath) => {
  try {
    if (!fs.existsSync(savePath)) return null;
    const stats = fs.statSync(savePath);
    return stats.mtime.toISOString().slice(0, 19);
  } catch {
    return null;
  }
});
electron.ipcMain.handle("dialog:openFolder", async () => {
  const result = await electron.dialog.showOpenDialog(mainWindow, { properties: ["openDirectory"] });
  return result.canceled ? null : result.filePaths[0];
});
electron.ipcMain.handle("device:probe", (_event, ip, port) => {
  return new Promise((resolve) => {
    const net = require("net");
    const socket = new net.Socket();
    let settled = false;
    const finish = (result) => {
      if (settled) return;
      settled = true;
      socket.destroy();
      resolve(result);
    };
    socket.setTimeout(2e3);
    socket.connect(port, ip, () => finish(true));
    socket.on("error", () => finish(false));
    socket.on("timeout", () => finish(false));
  });
});
function loadServerCfg() {
  let cfg = {};
  if (fs.existsSync(CONFIG_PATH)) {
    cfg = smolToml.parse(fs.readFileSync(CONFIG_PATH, "utf-8"));
  }
  const host = cfg.server_host || "localhost";
  const port = Number(cfg.server_port) || 8765;
  const pin = cfg.server_pin || "";
  const deviceId = cfg.device_id || "";
  const deviceName = cfg.device_name || "";
  const authHeaders = {
    "Authorization": `Bearer ${pin}`,
    "X-Device-ID": deviceId,
    "X-Device-Name": deviceName
  };
  return { host, port, authHeaders };
}
function findLatestFileInDir(dirPath) {
  try {
    if (!fs.existsSync(dirPath)) return null;
    let latestMs = 0;
    let latest = null;
    for (const e of fs.readdirSync(dirPath, { withFileTypes: true })) {
      if (!e.isFile()) continue;
      try {
        const fullPath = path.join(dirPath, e.name);
        const ms = fs.statSync(fullPath).mtimeMs;
        if (ms > latestMs) {
          latestMs = ms;
          latest = { path: fullPath, time: new Date(ms).toISOString().slice(0, 19) };
        }
      } catch {
      }
    }
    return latest;
  } catch {
    return null;
  }
}
electron.ipcMain.handle(
  "files:get-latest-in-folder",
  (_event, dirPath) => findLatestFileInDir(dirPath)
);
electron.ipcMain.handle("files:move-to-subfolder", (_event, { romPath, subfolderName, newSavePath, newStateFolder }) => {
  try {
    const newRomDir = path.join(path.dirname(romPath), subfolderName);
    fs.mkdirSync(newRomDir, { recursive: true });
    const newRomPath = path.join(newRomDir, path.basename(romPath));
    fs.renameSync(romPath, newRomPath);
    if (newSavePath && !fs.existsSync(newSavePath)) {
      fs.mkdirSync(path.dirname(newSavePath), { recursive: true });
      const base = path.basename(newSavePath, path.extname(newSavePath));
      const ext = path.extname(newSavePath).slice(1);
      const savesRoot = path.dirname(path.dirname(newSavePath));
      const flatLegacy = path.join(savesRoot, `${base}.${ext}`);
      if (fs.existsSync(flatLegacy)) {
        fs.renameSync(flatLegacy, newSavePath);
      } else {
        try {
          for (const e of fs.readdirSync(savesRoot, { withFileTypes: true })) {
            if (!e.isDirectory()) continue;
            const candidate = path.join(savesRoot, e.name, `${base}.${ext}`);
            if (fs.existsSync(candidate)) {
              fs.renameSync(candidate, newSavePath);
              break;
            }
          }
        } catch {
        }
      }
    }
    if (newStateFolder) {
      fs.mkdirSync(newStateFolder, { recursive: true });
      const base = path.basename(newStateFolder);
      const statesRoot = path.dirname(newStateFolder);
      const stateExts = ["state", "state.auto", "state1", "state2", "state3", "state4", "state5"];
      for (const ext of stateExts) {
        const src = path.join(statesRoot, `${base}.${ext}`);
        if (fs.existsSync(src)) fs.renameSync(src, path.join(newStateFolder, `${base}.${ext}`));
      }
      try {
        for (const e of fs.readdirSync(statesRoot, { withFileTypes: true })) {
          if (!e.isDirectory() || e.name === base) continue;
          for (const ext of stateExts) {
            const src = path.join(statesRoot, e.name, `${base}.${ext}`);
            if (fs.existsSync(src)) fs.renameSync(src, path.join(newStateFolder, `${base}.${ext}`));
          }
        }
      } catch {
      }
    }
    return { ok: true, newRomPath, newSavePath, newStateFolder };
  } catch (e) {
    return { ok: false, newRomPath: romPath, newSavePath, newStateFolder, error: e.message };
  }
});
electron.ipcMain.handle("save:push", async (_event, slug, savePath) => {
  try {
    if (!fs.existsSync(savePath)) return { ok: false, error: "Save file not found" };
    const { host, port, authHeaders } = loadServerCfg();
    const data = fs.readFileSync(savePath);
    const res = await fetch(`http://${host}:${port}/games/${slug}/save`, {
      method: "POST",
      headers: { ...authHeaders, "Content-Type": "application/octet-stream" },
      body: data,
      signal: AbortSignal.timeout(3e4)
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      return { ok: false, error: body.detail ?? res.statusText };
    }
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e.message || "Push failed" };
  }
});
electron.ipcMain.handle("save:pull", async (_event, slug, savePath) => {
  try {
    const { host, port, authHeaders } = loadServerCfg();
    const res = await fetch(`http://${host}:${port}/games/${slug}/save`, {
      headers: authHeaders,
      signal: AbortSignal.timeout(3e4)
    });
    if (res.status === 204) return { ok: true, pulled: false };
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      return { ok: false, pulled: false, error: body.detail ?? res.statusText };
    }
    const buf = Buffer.from(await res.arrayBuffer());
    if (fs.existsSync(savePath)) {
      fs.writeFileSync(`${savePath}.bak`, fs.readFileSync(savePath));
    }
    fs.mkdirSync(path.dirname(savePath), { recursive: true });
    fs.writeFileSync(savePath, buf);
    return { ok: true, pulled: true };
  } catch (e) {
    return { ok: false, pulled: false, error: e.message || "Pull failed" };
  }
});
electron.ipcMain.handle("state:push", async (_event, slug, statePath) => {
  try {
    if (!fs.existsSync(statePath)) return { ok: false, error: "State folder not found" };
    const tarResult = child_process.spawnSync("tar", ["-czf", "-", "-C", statePath, "."], {
      maxBuffer: 200 * 1024 * 1024
    });
    if (tarResult.error || tarResult.status !== 0) {
      return { ok: false, error: `Failed to compress state folder: ${tarResult.stderr?.toString().trim() ?? ""}` };
    }
    const data = tarResult.stdout;
    if (!data || data.length === 0) return { ok: false, error: "No state files to push" };
    const { host, port, authHeaders } = loadServerCfg();
    const res = await fetch(`http://${host}:${port}/games/${slug}/state`, {
      method: "POST",
      headers: { ...authHeaders, "Content-Type": "application/octet-stream" },
      body: data,
      signal: AbortSignal.timeout(6e4)
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      return { ok: false, error: body.detail ?? res.statusText };
    }
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e.message || "Push failed" };
  }
});
electron.ipcMain.handle("state:pull", async (_event, slug, statePath) => {
  try {
    const { host, port, authHeaders } = loadServerCfg();
    const res = await fetch(`http://${host}:${port}/games/${slug}/state`, {
      headers: authHeaders,
      signal: AbortSignal.timeout(6e4)
    });
    if (res.status === 204) return { ok: true, pulled: false };
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      return { ok: false, pulled: false, error: body.detail ?? res.statusText };
    }
    const buf = Buffer.from(await res.arrayBuffer());
    fs.mkdirSync(statePath, { recursive: true });
    const existing = fs.readdirSync(statePath).filter((f) => !f.endsWith(".bak"));
    for (const f of existing) {
      try {
        fs.renameSync(path.join(statePath, f), path.join(statePath, f + ".bak"));
      } catch {
      }
    }
    const extractResult = child_process.spawnSync("tar", ["-xzf", "-", "-C", statePath], {
      input: buf,
      maxBuffer: 200 * 1024 * 1024
    });
    if (extractResult.error || extractResult.status !== 0) {
      for (const f of existing) {
        const bak = path.join(statePath, f + ".bak");
        if (fs.existsSync(bak)) try {
          fs.renameSync(bak, path.join(statePath, f));
        } catch {
        }
      }
      return { ok: false, pulled: false, error: "Failed to extract state archive" };
    }
    for (const f of existing) {
      const bak = path.join(statePath, f + ".bak");
      if (fs.existsSync(bak)) try {
        fs.unlinkSync(bak);
      } catch {
      }
    }
    return { ok: true, pulled: true };
  } catch (e) {
    return { ok: false, pulled: false, error: e.message || "Pull failed" };
  }
});
electron.ipcMain.handle(
  "rom:push",
  async (_event, slug, toDeviceId, consoleName) => {
    try {
      let cfg = {};
      if (fs.existsSync(CONFIG_PATH)) {
        cfg = smolToml.parse(fs.readFileSync(CONFIG_PATH, "utf-8"));
      }
      const host = cfg.server_host || "localhost";
      const port = Number(cfg.server_port) || 8765;
      const pin = cfg.server_pin || "";
      const deviceId = cfg.device_id || "";
      const deviceName = cfg.device_name || "";
      const authHeaders = {
        "Authorization": `Bearer ${pin}`,
        "X-Device-ID": deviceId,
        "X-Device-Name": deviceName
      };
      const gdRes = await fetch(`http://${host}:${port}/games/${slug}/device`, { headers: authHeaders, signal: AbortSignal.timeout(5e3) });
      if (!gdRes.ok) return { ok: false, error: "This game is not configured on this device" };
      const gd = await gdRes.json();
      if (!gd.rom_path) return { ok: false, error: "No ROM path configured for this game" };
      if (!fs.existsSync(gd.rom_path)) return { ok: false, error: `ROM file not found: ${gd.rom_path}` };
      const consolesRes = await fetch(`http://${host}:${port}/devices/${toDeviceId}/consoles`, { headers: authHeaders, signal: AbortSignal.timeout(5e3) });
      if (!consolesRes.ok) return { ok: false, error: "Could not read target device configuration" };
      const consoles = await consolesRes.json();
      const match = consoles.find((c) => c.console_name === consoleName);
      if (!match?.device_game_folder) {
        return { ok: false, error: `${consoleName} is not configured on the target device yet` };
      }
      const romFilename = path.basename(gd.rom_path);
      const destinationPath = path.join(match.device_game_folder, romFilename);
      const fileSize = fs.statSync(gd.rom_path).size;
      const result = await new Promise((resolve, reject) => {
        const req = http.request(
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
              "X-Filename": romFilename
            }
          },
          (res) => {
            let body = "";
            res.on("data", (chunk) => {
              body += chunk.toString();
            });
            res.on("end", () => {
              if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) {
                try {
                  resolve(JSON.parse(body));
                } catch {
                  resolve({});
                }
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
        fs.createReadStream(gd.rom_path).pipe(req);
      });
      return { ok: true, targetOnline: result.target_online };
    } catch (e) {
      return { ok: false, error: e.message || "Push failed" };
    }
  }
);
electron.app.whenReady().then(() => {
  createWindow();
  electron.app.on("activate", () => {
    if (electron.BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});
electron.app.on("window-all-closed", () => {
  stopSyncDaemon();
  if (serverProcess) {
    serverProcess.kill("SIGKILL");
    serverProcess = null;
  }
  if (serverStartedByApp) {
    killServerByPid();
    void killOrphanServers();
  }
  if (process.platform !== "darwin") electron.app.quit();
});
