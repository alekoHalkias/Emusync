// Auto-update support via electron-updater (#634).
//
// Wraps electron-updater's autoUpdater, exposes IPC channels for the
// renderer to check/download/install updates, and forwards lifecycle
// events (update-available, update-downloaded, etc.) via
// win.webContents.send("updater:change", payload).
//
// The auto-update toggle is persisted in display.json alongside other
// display settings (scale, fullscreen, theme) — see display.ts.
import { autoUpdater } from "electron-updater";
import { ipcMain, BrowserWindow } from "electron";
import { rt } from "./runtime";
import { load as loadDisplay, save as saveDisplay } from "./display";

// ── autoUpdater configuration ────────────────────────────────────────────────

// Report progress to the renderer so the banner can show a timestamp.
autoUpdater.autoDownload = false; // only download on explicit user action

// ── event forwarding ─────────────────────────────────────────────────────────

type UpdateEvent =
  | { type: "update-available"; releaseNotes: string; releaseVersion: string }
  | { type: "update-not-available" }
  | { type: "update-downloaded"; releaseNotes: string; releaseVersion: string }
  | { type: "error"; message: string };

function forward(win: BrowserWindow, event: UpdateEvent): void {
  win.webContents.send("updater:change", event);
}

function attachListeners(win: BrowserWindow): void {
  autoUpdater.on("update-available", (info) =>
    forward(win, { type: "update-available", releaseNotes: typeof info.releaseNotes === "string" ? info.releaseNotes : "", releaseVersion: info.version }));
  autoUpdater.on("update-not-available", () =>
    forward(win, { type: "update-not-available" }));
  autoUpdater.on("update-downloaded", (info) =>
    forward(win, { type: "update-downloaded", releaseNotes: typeof info.releaseNotes === "string" ? info.releaseNotes : "", releaseVersion: info.version }));
  autoUpdater.on("error", (err) =>
    forward(win, { type: "error", message: err.message ?? String(err) }));
}

// ── IPC handlers ─────────────────────────────────────────────────────────────

export function registerUpdaterIpc(): void {
  ipcMain.handle("updater:check", async () => {
    const d = loadDisplay();
    if (!d.autoUpdateEnabled) return { available: false };
    try {
      const info = await autoUpdater.checkForUpdates();
      return { available: !!info };
    } catch (err: unknown) {
      return { available: false, error: err instanceof Error ? err.message : String(err) };
    }
  });

  ipcMain.handle("updater:download", async () => {
    try {
      await autoUpdater.downloadUpdate();
      return { ok: true };
    } catch (err: unknown) {
      return { ok: false, error: err instanceof Error ? err.message : String(err) };
    }
  });

  ipcMain.handle("updater:install", () => {
    autoUpdater.quitAndInstall(true, true);
    return { ok: true };
  });

  ipcMain.handle("updater:getEnabled", () => {
    const d = loadDisplay();
    return d.autoUpdateEnabled;
  });

  ipcMain.handle("updater:setEnabled", (_e, enabled: boolean) => {
    const d = loadDisplay();
    saveDisplay({ ...d, autoUpdateEnabled: enabled });
    return enabled;
  });

  const check = () => {
    if (loadDisplay().autoUpdateEnabled) autoUpdater.checkForUpdates().catch(() => {});
  };
  // Listeners attach once, when the window first exists; then check now and every 4 hours.
  let attached = false;
  const attachWhenReady = () => {
    const win = rt.mainWindow;
    if (!win || attached) return;
    attached = true;
    attachListeners(win);
    check();
    setInterval(check, 4 * 60 * 60 * 1000);
  };
  attachWhenReady();
  // createWindow assigns rt.mainWindow after IPC registration.
  setTimeout(attachWhenReady, 1000);
}
