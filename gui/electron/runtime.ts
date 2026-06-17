// Shared constants and mutable runtime state for the Electron main process.
//
// Long-lived handles (server/game/daemon processes, the window) and the
// console-definition caches are reassigned from several modules. ES modules
// only export read-only bindings, so they live as properties on the single
// `rt` object — property writes propagate across importers, plain `let`
// reassignment would not.
import type { ChildProcess } from "child_process";
import type { BrowserWindow } from "electron";
import { existsSync } from "fs";
import { join, dirname } from "path";
import { homedir } from "os";

export const CONFIG_PATH = join(homedir(), ".emusync", "emusync.toml");
export const SCRIPT = process.env.EMUSYNC_SCRIPT ?? join(__dirname, "../../../emusync.py");
export const PYTHON = process.env.EMUSYNC_PYTHON ?? (() => {
  const venv = join(dirname(SCRIPT), ".venv", "bin", "python");
  return existsSync(venv) ? venv : "python3";
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
