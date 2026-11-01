// Shared constants and mutable runtime state for the Electron main process.
//
// Long-lived handles (server/game/daemon processes, the window) and the
// console-definition caches are reassigned from several modules. ES modules
// only export read-only bindings, so they live as properties on the single
// `rt` object — property writes propagate across importers, plain `let`
// reassignment would not.
import type { ChildProcess } from "child_process";
import { app, type BrowserWindow } from "electron";
import { existsSync } from "fs";
import { join, dirname } from "path";
import { CONFIG_PATH, cacheDir } from "./paths";

export { CONFIG_PATH };
// A packaged Linux AppImage mounts read-only at a random path, so its bundled CLI is
// copied to a stable runtime dir laid out like a checkout (runtimeSetup.ts, #677).
export const RUNTIME_DIR = join(cacheDir(), "runtime");
export const USE_RUNTIME_DIR = !process.env.EMUSYNC_SCRIPT && app.isPackaged && !!process.env.APPIMAGE;
export const SCRIPT = process.env.EMUSYNC_SCRIPT
  ?? (USE_RUNTIME_DIR ? join(RUNTIME_DIR, "src/emusync.py") : join(__dirname, "../../../emusync.py"));
export const LAUNCHER = join(dirname(SCRIPT), "emusync");
export const PYTHON = process.env.EMUSYNC_PYTHON ?? (() => {
  const win = process.platform === "win32";
  const venv = join(dirname(SCRIPT), "../.cache/.venv", win ? "Scripts" : "bin", win ? "python.exe" : "python");
  // In the runtime dir the venv is created by ensureRuntime, so it may not exist yet at import.
  return existsSync(venv) || USE_RUNTIME_DIR ? venv : win ? "python" : "python3";
})();

export const rt = {
  serverProcess: null as ChildProcess | null,
  serverStartedByApp: false,
  gameProcess: null as ChildProcess | null,
  syncDaemonProcess: null as ChildProcess | null,
  syncDaemonRestartTimer: null as ReturnType<typeof setTimeout> | null,
  mainWindow: null as BrowserWindow | null,

  // Console definitions loaded once from the Python API (see emulator/console-defs)
  cachedConsoleDefs: null as Record<string, any> | null,
  cachedSystemDefs: null as Record<string, any> | null,
  cachedConsoleFolderNames: null as Record<string, string[]> | null,
};
