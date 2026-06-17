// Filesystem IPC: dialogs, save-file helpers, the move-to-subfolder migration,
// and a TCP reachability probe.
import { ipcMain, dialog } from "electron";
import { existsSync, writeFileSync, mkdirSync, readdirSync, statSync, renameSync } from "fs";
import { join, dirname, basename, extname } from "path";
import { rt } from "./runtime";

/** Newest file in a directory, or null if the dir is empty/missing. */
export function findLatestFileInDir(dirPath: string): { path: string; time: string } | null {
  try {
    if (!existsSync(dirPath)) return null;
    let latestMs = 0;
    let latest: { path: string; time: string } | null = null;
    for (const e of readdirSync(dirPath, { withFileTypes: true })) {
      if (!e.isFile()) continue;
      try {
        const fullPath = join(dirPath, e.name);
        const ms = statSync(fullPath).mtimeMs;
        if (ms > latestMs) {
          latestMs = ms;
          latest = { path: fullPath, time: new Date(ms).toISOString().slice(0, 19) };
        }
      } catch {}
    }
    return latest;
  } catch { return null; }
}

export function registerFilesIpc(): void {
  ipcMain.handle("dialog:openFile", async (_event, options: Electron.OpenDialogOptions) => {
    const result = await dialog.showOpenDialog(rt.mainWindow!, options);
    return result.canceled ? null : result.filePaths[0];
  });

  ipcMain.handle("dialog:openFolder", async () => {
    const result = await dialog.showOpenDialog(rt.mainWindow!, { properties: ["openDirectory"] });
    return result.canceled ? null : result.filePaths[0];
  });

  // Create an empty save file (+ parent dirs) if it doesn't already exist
  ipcMain.handle("files:ensure-save", (_event, savePath: string): { created: boolean } => {
    try {
      if (existsSync(savePath)) return { created: false };
      mkdirSync(dirname(savePath), { recursive: true });
      writeFileSync(savePath, Buffer.alloc(0));
      return { created: true };
    } catch { return { created: false }; }
  });

  // Get the last modified time of a save file
  ipcMain.handle("files:get-save-time", (_event, savePath: string): string | null => {
    try {
      if (!existsSync(savePath)) return null;
      const stats = statSync(savePath);
      return stats.mtime.toISOString().slice(0, 19);
    } catch { return null; }
  });

  ipcMain.handle("files:get-latest-in-folder", (_event, dirPath: string) =>
    findLatestFileInDir(dirPath)
  );

  // TCP probe — resolves true if a TCP connection to ip:port succeeds within 2 s
  ipcMain.handle("device:probe", (_event, ip: string, port: number): Promise<boolean> => {
    return new Promise((resolve) => {
      const net = require("net");
      const socket = new net.Socket();
      let settled = false;
      const finish = (result: boolean) => {
        if (settled) return;
        settled = true;
        socket.destroy();
        resolve(result);
      };
      socket.setTimeout(2000);
      socket.connect(port, ip, () => finish(true));
      socket.on("error", () => finish(false));
      socket.on("timeout", () => finish(false));
    });
  });

  ipcMain.handle("files:move-to-subfolder", (
    _event,
    { romPath, subfolderName, newSavePath, newStateFolder }: {
      romPath: string;
      subfolderName: string;
      newSavePath: string;     // canonical target: savesRoot/GameName/base.ext
      newStateFolder: string;  // canonical target folder: statesRoot/GameName/
    }
  ): { ok: boolean; newRomPath: string; newSavePath: string; newStateFolder: string; error?: string } => {
    try {
      // ── ROM ───────────────────────────────────────────────────────────────────
      const newRomDir = join(dirname(romPath), subfolderName);
      mkdirSync(newRomDir, { recursive: true });
      const newRomPath = join(newRomDir, basename(romPath));
      renameSync(romPath, newRomPath);

      // ── Save file ─────────────────────────────────────────────────────────────
      // Target: savesRoot/GameName/base.ext.
      // If not already there, search common legacy locations and migrate.
      if (newSavePath && !existsSync(newSavePath)) {
        mkdirSync(dirname(newSavePath), { recursive: true });
        const base     = basename(newSavePath, extname(newSavePath));
        const ext      = extname(newSavePath).slice(1);
        // savesRoot = two levels up from the file (…/GameName/base.ext → …/)
        const savesRoot = dirname(dirname(newSavePath));
        // Check legacy patterns: flat root, then any immediate subdir (core folders)
        const flatLegacy = join(savesRoot, `${base}.${ext}`);
        if (existsSync(flatLegacy)) {
          renameSync(flatLegacy, newSavePath);
        } else {
          try {
            for (const e of readdirSync(savesRoot, { withFileTypes: true })) {
              if (!e.isDirectory()) continue;
              const candidate = join(savesRoot, e.name, `${base}.${ext}`);
              if (existsSync(candidate)) { renameSync(candidate, newSavePath); break; }
            }
          } catch {}
        }
      }

      // ── State folder ──────────────────────────────────────────────────────────
      // Target: statesRoot/GameName/ (folder, not a file).
      // Create it and migrate any existing state files from legacy locations.
      if (newStateFolder) {
        mkdirSync(newStateFolder, { recursive: true });
        const base        = basename(newStateFolder);  // = subfolderName = game base name
        const statesRoot  = dirname(newStateFolder);
        const stateExts   = ["state", "state.auto", "state1", "state2", "state3", "state4", "state5"];
        // Migrate flat root files: statesRoot/base.stateN
        for (const ext of stateExts) {
          const src = join(statesRoot, `${base}.${ext}`);
          if (existsSync(src)) renameSync(src, join(newStateFolder, `${base}.${ext}`));
        }
        // Migrate from any core-subfolder: statesRoot/mGBA/base.stateN
        try {
          for (const e of readdirSync(statesRoot, { withFileTypes: true })) {
            if (!e.isDirectory() || e.name === base) continue;
            for (const ext of stateExts) {
              const src = join(statesRoot, e.name, `${base}.${ext}`);
              if (existsSync(src)) renameSync(src, join(newStateFolder, `${base}.${ext}`));
            }
          }
        } catch {}
      }

      return { ok: true, newRomPath, newSavePath, newStateFolder };
    } catch (e: any) {
      return { ok: false, newRomPath: romPath, newSavePath, newStateFolder, error: e.message };
    }
  });
}
