// Main application window.
import { BrowserWindow, shell } from "electron";
import { join } from "path";
import { rt } from "./runtime";

export function createWindow(): void {
  rt.mainWindow = new BrowserWindow({
    width: 900,
    height: 650,
    minWidth: 700,
    minHeight: 500,
    title: "EmuSync",
    autoHideMenuBar: true,
    webPreferences: {
      preload: join(__dirname, "../preload/preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (process.env.NODE_ENV === "development") {
    rt.mainWindow.loadURL("http://localhost:5173");
  } else {
    rt.mainWindow.loadFile(join(__dirname, "../renderer/index.html"));
  }

  rt.mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  // Electron's default zoom-in accelerator is CmdOrCtrl+Plus, which on a US
  // keyboard means Shift+= — the bare Ctrl+= (same physical key, no shift)
  // isn't bound, unlike Ctrl+- (zoom out) and Ctrl+0 (reset). Add just that
  // missing case; Shift+= keeps working via the default menu as before.
  rt.mainWindow.webContents.on("before-input-event", (_event, input) => {
    if (input.control && input.key === "=" && input.type === "keyDown") {
      const wc = rt.mainWindow?.webContents;
      if (wc) wc.setZoomLevel(wc.getZoomLevel() + 0.5);
    }
  });
}
