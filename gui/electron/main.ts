import { app, BrowserWindow, dialog, ipcMain, shell } from "electron";
import { spawn, ChildProcess } from "child_process";
import { existsSync, readFileSync, writeFileSync, unlinkSync, mkdirSync } from "fs";
import { join, dirname } from "path";
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
  }
  gameProcess = null;
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
