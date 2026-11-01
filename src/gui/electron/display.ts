// Display settings (#499): UI zoom + fullscreen, persisted to
// <config dir>/display.json. Deliberately NOT in emusync.toml — src/server/config.py's
// save() rebuilds that file from its dataclass and would drop unknown keys.
import { BrowserWindow, ipcMain } from "electron";
import { existsSync, readFileSync, writeFileSync, mkdirSync } from "fs";
import { dirname, join } from "path";
import { configDir } from "./paths";
import { rt } from "./runtime";

const DISPLAY_PATH = join(configDir(), "display.json");
const SCALES = [1, 1.25, 1.5, 2];

interface Display { scale: number; fullscreen: boolean; autoUpdateEnabled: boolean }

export { load, save };

function load(): Display {
  let saved: Partial<Display> = {};
  try {
    if (existsSync(DISPLAY_PATH)) saved = JSON.parse(readFileSync(DISPLAY_PATH, "utf-8"));
  } catch { /* corrupt file — fall back to defaults */ }
  // First run (nothing saved): fullscreen via --fullscreen or on Steam Deck/SteamOS.
  const autoFullscreen = process.argv.includes("--fullscreen") || !!process.env.SteamDeck || !!process.env.SteamOS;
  // Steam sets these for every launch, including non-Steam shortcuts (#673).
  const steamLaunch = !!process.env.SteamGameId || !!process.env.SteamAppId;
  return {
    scale: SCALES.includes(saved.scale as number) ? (saved.scale as number) : 1,
    fullscreen: process.argv.includes("--fullscreen") || steamLaunch || (saved.fullscreen ?? autoFullscreen),
    autoUpdateEnabled: saved.autoUpdateEnabled ?? true,
  };
}

function save(d: Display): void {
  mkdirSync(dirname(DISPLAY_PATH), { recursive: true });
  writeFileSync(DISPLAY_PATH, JSON.stringify(d));
}

export function applyDisplay(win: BrowserWindow): void {
  const d = load();
  win.setFullScreen(d.fullscreen);
  // Zoom resets on each navigation, so re-apply after every load.
  let ready = false;
  win.webContents.on("did-finish-load", () => {
    win.webContents.setZoomFactor(d.scale);
    ready = true;
  });
  // Entering/leaving fullscreen by any route (F11, Alt+Enter, button, OS) is
  // persisted. Ignored until the page has loaded so restoring saved state at
  // startup doesn't clobber it.
  const sync = (fullscreen: boolean) => {
    if (!ready) return;
    save({ ...load(), fullscreen });
    win.webContents.send("display:changed", { fullscreen });
  };
  win.on("enter-full-screen", () => sync(true));
  win.on("leave-full-screen", () => sync(false));
}

export function toggleFullscreen(): boolean {
  const win = rt.mainWindow;
  if (!win) return false;
  const fullscreen = !win.isFullScreen();
  win.setFullScreen(fullscreen);
  save({ ...load(), fullscreen });
  return fullscreen;
}

export function registerDisplayIpc(): void {
  ipcMain.handle("display:get", () => ({
    scale: load().scale,
    fullscreen: !!rt.mainWindow?.isFullScreen(),
    autoUpdateEnabled: load().autoUpdateEnabled,
  }));

  ipcMain.handle("display:cycleScale", () => {
    const d = load();
    const scale = SCALES[(SCALES.indexOf(d.scale) + 1) % SCALES.length];
    rt.mainWindow?.webContents.setZoomFactor(scale);
    save({ ...d, scale });
    return scale;
  });

  ipcMain.handle("display:toggleFullscreen", () => toggleFullscreen());
}
