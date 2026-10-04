// Big Picture display settings (#499): UI zoom + fullscreen, persisted to
// ~/.emusync/display.json. Deliberately NOT in emusync.toml — server/config.py's
// save() rebuilds that file from its dataclass and would drop unknown keys.
import { BrowserWindow, ipcMain } from "electron";
import { existsSync, readFileSync, writeFileSync, mkdirSync } from "fs";
import { dirname, join } from "path";
import { homedir } from "os";
import { rt } from "./runtime";

const DISPLAY_PATH = join(homedir(), ".emusync", "display.json");
const SCALES = [1, 1.25, 1.5, 2];

interface Display { scale: number; fullscreen: boolean; bigPicture: boolean }

function load(): Display {
  let saved: Partial<Display> = {};
  try {
    if (existsSync(DISPLAY_PATH)) saved = JSON.parse(readFileSync(DISPLAY_PATH, "utf-8"));
  } catch { /* corrupt file — fall back to defaults */ }
  // First run (nothing saved): fullscreen via --fullscreen or on Steam Deck/SteamOS.
  const autoFullscreen = process.argv.includes("--fullscreen") || !!process.env.SteamDeck || !!process.env.SteamOS;
  return {
    scale: SCALES.includes(saved.scale as number) ? (saved.scale as number) : 1,
    fullscreen: process.argv.includes("--fullscreen") || (saved.fullscreen ?? autoFullscreen),
    // Big Picture theme/wheel (#503): same first-run default as fullscreen, but toggled independently.
    bigPicture: process.argv.includes("--fullscreen") || (saved.bigPicture ?? autoFullscreen),
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
  win.webContents.on("did-finish-load", () => win.webContents.setZoomFactor(d.scale));
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
    bigPicture: load().bigPicture,
  }));

  ipcMain.handle("display:toggleBigPicture", () => {
    const d = load();
    save({ ...d, bigPicture: !d.bigPicture });
    return !d.bigPicture;
  });

  ipcMain.handle("display:cycleScale", () => {
    const d = load();
    const scale = SCALES[(SCALES.indexOf(d.scale) + 1) % SCALES.length];
    rt.mainWindow?.webContents.setZoomFactor(scale);
    save({ ...d, scale });
    return scale;
  });

  ipcMain.handle("display:toggleFullscreen", () => toggleFullscreen());
}
