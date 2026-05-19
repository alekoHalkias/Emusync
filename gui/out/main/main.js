"use strict";
const electron = require("electron");
const child_process = require("child_process");
const fs = require("fs");
const path = require("path");
const os = require("os");
const smolToml = require("smol-toml");
const CONFIG_PATH = path.join(os.homedir(), ".emusync", "emusync.toml");
const PYTHON = process.env.EMUSYNC_PYTHON ?? "python3";
const SCRIPT = process.env.EMUSYNC_SCRIPT ?? path.join(__dirname, "../../emusync.py");
let serverProcess = null;
let mainWindow = null;
function createWindow() {
  mainWindow = new electron.BrowserWindow({
    width: 900,
    height: 650,
    minWidth: 700,
    minHeight: 500,
    title: "EmuSync",
    webPreferences: {
      preload: path.join(__dirname, "../preload/preload.js"),
      contextIsolation: true,
      nodeIntegration: false
    }
  });
  if (process.env.NODE_ENV === "development") {
    mainWindow.loadURL("http://localhost:5173");
    mainWindow.webContents.openDevTools();
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
electron.ipcMain.handle("server:start", () => {
  if (serverProcess) return { ok: true, token: null };
  return new Promise((resolve) => {
    let token = null;
    const proc = child_process.spawn(PYTHON, [SCRIPT, "server", "start"], {
      stdio: ["ignore", "pipe", "pipe"]
    });
    serverProcess = proc;
    proc.stdout?.on("data", (chunk) => {
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
    setTimeout(() => {
      if (token === null) resolve({ ok: true, token: null });
    }, 5e3);
  });
});
electron.ipcMain.handle("server:stop", () => {
  serverProcess?.kill("SIGTERM");
  serverProcess = null;
  return true;
});
electron.ipcMain.handle("dialog:openFile", async (_event, options) => {
  const result = await electron.dialog.showOpenDialog(mainWindow, options);
  return result.canceled ? null : result.filePaths[0];
});
electron.app.whenReady().then(() => {
  createWindow();
  electron.app.on("activate", () => {
    if (electron.BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});
electron.app.on("window-all-closed", () => {
  serverProcess?.kill("SIGTERM");
  if (process.platform !== "darwin") electron.app.quit();
});
