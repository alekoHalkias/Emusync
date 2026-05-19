import { app, BrowserWindow, dialog, ipcMain } from "electron";
import { ChildProcess, spawn } from "child_process";
import * as path from "path";
import * as fs from "fs";
import * as os from "os";

let mainWindow: BrowserWindow | null = null;
let backendProcess: ChildProcess | null = null;

const CONFIG_FILE = path.join(os.homedir(), ".emusync", "emusync.toml");
const BACKEND_PORT = 8765;

function getBackendArgs(): { cmd: string; args: string[] } {
  if (app.isPackaged) {
    const bin = path.join(process.resourcesPath, "emusync-backend");
    return { cmd: bin, args: ["server", "start"] };
  }
  const script = path.join(__dirname, "..", "..", "backend", "cli.py");
  return { cmd: "python3", args: [script, "server", "start"] };
}

function startBackend(): Promise<void> {
  return new Promise((resolve, reject) => {
    const { cmd, args } = getBackendArgs();
    backendProcess = spawn(cmd, args, {
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env },
    });

    let ready = false;
    backendProcess.stdout?.on("data", (data: Buffer) => {
      const text = data.toString();
      console.log("[backend]", text.trim());
      if (!ready && text.includes("running on")) {
        ready = true;
        resolve();
      }
    });

    backendProcess.stderr?.on("data", (data: Buffer) => {
      console.error("[backend err]", data.toString().trim());
    });

    backendProcess.on("error", reject);
    backendProcess.on("exit", (code) => {
      if (!ready) reject(new Error(`Backend exited with code ${code}`));
    });

    // Resolve after 3s even if we don't see the ready message
    setTimeout(() => {
      if (!ready) {
        ready = true;
        resolve();
      }
    }, 3000);
  });
}

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 900,
    height: 650,
    minWidth: 700,
    minHeight: 500,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
    title: "EmuSync",
    backgroundColor: "#1a1a2e",
  });

  mainWindow.loadFile(path.join(__dirname, "..", "renderer", "index.html"));
  mainWindow.on("closed", () => { mainWindow = null; });
}

// ── IPC handlers ───────────────────────────────────────────────────────────

ipcMain.handle("check-config", () => {
  const exists = fs.existsSync(CONFIG_FILE);
  return { configExists: exists };
});

ipcMain.handle("get-backend-port", () => BACKEND_PORT);

ipcMain.handle("open-file-dialog", async (_event, options?: Electron.OpenDialogOptions) => {
  if (!mainWindow) return null;
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ["openFile"],
    ...options,
  });
  return result.canceled ? null : result.filePaths[0];
});

ipcMain.handle("open-directory-dialog", async () => {
  if (!mainWindow) return null;
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ["openDirectory"],
  });
  return result.canceled ? null : result.filePaths[0];
});

// ── App lifecycle ──────────────────────────────────────────────────────────

app.whenReady().then(async () => {
  try {
    await startBackend();
  } catch (err) {
    console.error("Backend failed to start:", err);
  }
  createWindow();
});

app.on("window-all-closed", () => {
  if (backendProcess) backendProcess.kill();
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (mainWindow === null) createWindow();
});

app.on("before-quit", () => {
  if (backendProcess) backendProcess.kill();
});
