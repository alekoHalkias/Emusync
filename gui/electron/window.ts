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
}
