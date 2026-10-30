// Electron main-process entry point.
//
// This file only wires things together: it registers every domain's IPC
// handlers and owns the app lifecycle. The actual logic lives in the
// per-domain modules imported below (see runtime.ts for the shared state).
import "./migrate"; // must run first: moves a legacy ~/.emusync before any module reads paths (#564)
import { app, BrowserWindow } from "electron";
import { rt } from "./runtime";
import { createWindow } from "./window";
import { registerConfigIpc } from "./config-store";
import { registerDisplayIpc } from "./display";
import { registerServerIpc, stopSyncDaemon, killServerByPid, killOrphanServers } from "./server";
import { registerGameIpc } from "./game";
import { registerFilesIpc } from "./files";
import { registerGameFolderIpc } from "./gamefolder";
import { registerSwitchModsIpc } from "./switchmods";
import { registerSyncIpc } from "./sync";
import { registerEmulatorIpc } from "./emulator/ipc";
import { registerArtIpc } from "./art";
import { registerArtworkIpc } from "./artwork";
import { registerSteamGridDbIpc } from "./steamgriddb";
import { registerSteamIpc } from "./steam";
import { registerSwitchTitleDbIpc } from "./switchtitledb";
import { registerThemeScheme, ThemeEngine } from "./themes";
import { registerUpdaterIpc } from "./updater";

// Register all IPC handlers up front (renderer can only call them once a window
// has loaded, which happens after app.whenReady below).
registerThemeScheme();
registerConfigIpc();
registerDisplayIpc();
registerServerIpc();
registerGameIpc();
registerFilesIpc();
registerGameFolderIpc();
registerSwitchModsIpc();
registerSyncIpc();
registerEmulatorIpc();
registerArtIpc();
registerArtworkIpc();
registerSteamGridDbIpc();
registerSteamIpc();
registerSwitchTitleDbIpc();
ThemeEngine.registerIpc();
registerUpdaterIpc();

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
