// Config file (~/.emusync/emusync.toml) reading/writing.
//   - config:* IPC handlers used by the renderer
//   - loadServerCfg(): the {host, port, authHeaders} every networked handler needs
import { ipcMain } from "electron";
import { existsSync, readFileSync, writeFileSync, mkdirSync } from "fs";
import { dirname } from "path";
import { parse as parseTOML, stringify as stringifyTOML } from "smol-toml";
import { CONFIG_PATH } from "./runtime";

export function loadServerCfg(): { host: string; port: number; authHeaders: Record<string, string> } {
  let cfg: Record<string, any> = {};
  if (existsSync(CONFIG_PATH)) {
    cfg = parseTOML(readFileSync(CONFIG_PATH, "utf-8")) as Record<string, any>;
  }
  const host = (cfg.server_host as string) || "localhost";
  const port = Number(cfg.server_port) || 8765;
  const pin  = (cfg.server_pin as string) || "";
  const deviceId   = (cfg.device_id as string) || "";
  const deviceName = (cfg.device_name as string) || "";
  const authHeaders: Record<string, string> = {
    "Authorization": `Bearer ${pin}`,
    "X-Device-ID": deviceId,
    "X-Device-Name": deviceName,
  };
  return { host, port, authHeaders };
}

export function registerConfigIpc(): void {
  ipcMain.handle("config:load", () => {
    if (!existsSync(CONFIG_PATH)) return null;
    try {
      return parseTOML(readFileSync(CONFIG_PATH, "utf-8"));
    } catch {
      return null;
    }
  });

  ipcMain.handle("config:save", (_event, data: Record<string, unknown>) => {
    mkdirSync(dirname(CONFIG_PATH), { recursive: true });
    writeFileSync(CONFIG_PATH, stringifyTOML(data as any));
    return true;
  });

  ipcMain.handle("config:exists", () => existsSync(CONFIG_PATH));

  ipcMain.handle("config:getRecentFolders", (_event, consoleKey: string) => {
    if (!existsSync(CONFIG_PATH)) return [];
    try {
      const data = parseTOML(readFileSync(CONFIG_PATH, "utf-8"));
      const recentFolders = (data.recent_import_folders as Record<string, any>) || {};
      return recentFolders[consoleKey] || [];
    } catch {
      return [];
    }
  });

  ipcMain.handle("config:addRecentFolder", (_event, consoleKey: string, folderPath: string) => {
    if (!existsSync(CONFIG_PATH)) return;
    try {
      const data = parseTOML(readFileSync(CONFIG_PATH, "utf-8"));
      if (!data.recent_import_folders) {
        data.recent_import_folders = {};
      }
      const recentFolders = (data.recent_import_folders as Record<string, any>);
      if (!recentFolders[consoleKey]) {
        recentFolders[consoleKey] = [];
      }
      const folders = recentFolders[consoleKey] as string[];
      // Remove if already exists (will re-add at start)
      const index = folders.indexOf(folderPath);
      if (index !== -1) {
        folders.splice(index, 1);
      }
      // Add to front and limit to 10 recent folders
      folders.unshift(folderPath);
      folders.splice(10);
      writeFileSync(CONFIG_PATH, stringifyTOML(data as any));
    } catch {
      // ignore
    }
  });
}
