import { app, BrowserWindow, dialog, ipcMain, shell } from "electron";
import { spawn, ChildProcess } from "child_process";
import { existsSync, readFileSync, writeFileSync, mkdirSync } from "fs";
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
let gameProcess: ChildProcess | null = null;
let mainWindow: BrowserWindow | null = null;


function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 900,
    height: 650,
    minWidth: 700,
    minHeight: 500,
    title: "EmuSync",
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

ipcMain.handle("server:start", () => {
  if (serverProcess) return { ok: true, token: null };

  return new Promise<{ ok: boolean; token: string | null }>((resolve) => {
    let token: string | null = null;
    const proc = spawn(PYTHON, [SCRIPT, "server", "start"], {
      stdio: ["ignore", "pipe", "pipe"],
    });
    serverProcess = proc;

    proc.stdout?.on("data", (chunk: Buffer) => {
      const line = chunk.toString();
      const match = line.match(/Pairing token: (\S+)/);
      if (match) {
        token = match[1];
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
    });

    // Timeout in case the server starts but doesn't print the token
    setTimeout(() => {
      if (token === null) resolve({ ok: true, token: null });
    }, 5000);
  });
});

ipcMain.handle("server:stop", () => {
  serverProcess?.kill("SIGTERM");
  serverProcess = null;
  return true;
});

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

// ── app lifecycle ─────────────────────────────────────────────────────────────

app.whenReady().then(() => {
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  serverProcess?.kill("SIGTERM");
  if (process.platform !== "darwin") app.quit();
});
