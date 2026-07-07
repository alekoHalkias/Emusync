// Electron main-process entry point.
//
// This file only wires things together: it registers every domain's IPC
// handlers and owns the app lifecycle. The actual logic lives in the
// per-domain modules imported below (see runtime.ts for the shared state).
import { app, BrowserWindow } from "electron";
import { rt } from "./runtime";
import { createWindow } from "./window";
import { registerConfigIpc } from "./config-store";
import { registerServerIpc, stopSyncDaemon, killServerByPid, killOrphanServers } from "./server";
import { registerGameIpc } from "./game";
import { registerFilesIpc } from "./files";
import { registerSyncIpc } from "./sync";
import { registerEmulatorIpc } from "./emulator/ipc";
import { registerArtIpc } from "./art";
import { registerSteamGridDbIpc } from "./steamgriddb";

// Register all IPC handlers up front (renderer can only call them once a window
// has loaded, which happens after app.whenReady below).
registerConfigIpc();
registerServerIpc();
registerGameIpc();
registerFilesIpc();
registerSyncIpc();
registerEmulatorIpc();
registerArtIpc();
registerSteamGridDbIpc();

// ── app lifecycle ─────────────────────────────────────────────────────────────

app.whenReady().then(() => {
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  stopSyncDaemon();
  if (rt.serverProcess) {
    rt.serverProcess.kill("SIGKILL");
    rt.serverProcess = null;
  }
  if (rt.serverStartedByApp) {
    killServerByPid();
    void killOrphanServers();
  }
  if (process.platform !== "darwin") app.quit();
});
