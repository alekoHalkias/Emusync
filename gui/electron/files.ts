// Filesystem IPC: dialogs, save-file helpers, the rename-game-files migration,
// and a TCP reachability probe.
import { ipcMain, dialog } from "electron";
import { existsSync, writeFileSync, readFileSync, mkdirSync, readdirSync, statSync, renameSync } from "fs";
import { homedir } from "os";
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

  // PS2 per-game last-played from PCSX2's playtime.dat (issue #301). `emusync run`
  // learns each game's disc serial into ~/.emusync/ps2_serials.json; here we join
  // that with the live playtime.dat (serial → last-played) so the game list can
  // show a real per-game date despite the shared memory card. Returns {slug: ISO}.
  ipcMain.handle("files:get-ps2-last-played", (): Record<string, string> => {
    const out: Record<string, string> = {};
    try {
      const home = homedir();
      const mapPath = join(home, ".emusync", "ps2_serials.json");
      if (!existsSync(mapPath)) return out;
      const map = JSON.parse(readFileSync(mapPath, "utf-8")) as Record<string, string>;

      const ptFile = [
        join(home, ".config/PCSX2/inis/playtime.dat"),
        join(home, ".var/app/net.pcsx2.PCSX2/config/PCSX2/inis/playtime.dat"),
      ].find(p => existsSync(p));
      if (!ptFile) return out;

      const lastPlayed: Record<string, number> = {};
      for (const line of readFileSync(ptFile, "utf-8").split("\n")) {
        const parts = line.trim().split(/\s+/);
        if (parts.length >= 3) {
          const lp = parseInt(parts[2], 10);
          if (!isNaN(lp)) lastPlayed[parts[0]] = lp;
        }
      }
      for (const [slug, serial] of Object.entries(map)) {
        const lp = lastPlayed[serial];
        if (lp) out[slug] = new Date(lp * 1000).toISOString();
      }
    } catch { /* best effort — no PS2 activity shown */ }
    return out;
  });

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

  // Rename a game's on-disk artifacts to a cleaned title (issue #283), and/or
  // organise a flat ROM into a per-game subfolder. Generalises the old
  // move-to-subfolder migration: the ROM file (and an optional second copy, e.g.
  // a network ROM's local copy) is renamed to `newBase`, and the save file +
  // state folder are renamed to match. Save/state targets are recomputed from
  // `newBase` under the same roots; the current paths (and legacy locations) are
  // migrated into them. Renames are best-effort no-ops when a source is missing
  // or already at the target, so calling with an unchanged name is safe.
  ipcMain.handle("files:rename-game-files", (
    _event,
    { romPath, savePath, stateFolder, newBase, reorganize, secondaryRomPath }: {
      romPath: string;
      savePath: string;        // current canonical save: savesRoot/OldName/old.ext
      stateFolder: string;     // current canonical state folder: statesRoot/OldName/
      newBase: string;         // sanitized title (filesystem-safe)
      reorganize: boolean;     // true: nest ROM under <dir>/<newBase>/; false: rename in place
      secondaryRomPath?: string;
    }
  ): { ok: boolean; newRomPath: string; newSavePath: string; newStateFolder: string; newSecondaryRomPath?: string; error?: string } => {
    let newSavePath = savePath;
    let newStateFolder = stateFolder;
    try {
      const oldBase = basename(romPath, extname(romPath));

      // ── ROM ───────────────────────────────────────────────────────────────────
      const newRomDir = reorganize ? join(dirname(romPath), newBase) : dirname(romPath);
      mkdirSync(newRomDir, { recursive: true });
      const newRomPath = join(newRomDir, newBase + extname(romPath));
      if (newRomPath !== romPath && existsSync(romPath)) renameSync(romPath, newRomPath);

      // ── Secondary ROM copy (e.g. a "both" network ROM's local copy) ───────────
      let newSecondaryRomPath: string | undefined;
      if (secondaryRomPath) {
        newSecondaryRomPath = join(dirname(secondaryRomPath), newBase + extname(secondaryRomPath));
        if (newSecondaryRomPath !== secondaryRomPath && existsSync(secondaryRomPath)) {
          renameSync(secondaryRomPath, newSecondaryRomPath);
        }
      }

      // ── Save file ─────────────────────────────────────────────────────────────
      // Target: savesRoot/newBase/newBase.ext. Migrate the current save if present,
      // else search common legacy locations (by the OLD base) and migrate.
      if (savePath) {
        const saveExt   = extname(savePath);
        const savesRoot = dirname(dirname(savePath));   // …/OldName/old.ext → …/
        newSavePath     = join(savesRoot, newBase, newBase + saveExt);
        if (newSavePath !== savePath) {
          mkdirSync(dirname(newSavePath), { recursive: true });
          if (existsSync(savePath)) {
            renameSync(savePath, newSavePath);
          } else {
            const ext = saveExt.slice(1);
            const flatLegacy = join(savesRoot, `${oldBase}.${ext}`);
            if (existsSync(flatLegacy)) {
              renameSync(flatLegacy, newSavePath);
            } else {
              try {
                for (const e of readdirSync(savesRoot, { withFileTypes: true })) {
                  if (!e.isDirectory()) continue;
                  const candidate = join(savesRoot, e.name, `${oldBase}.${ext}`);
                  if (existsSync(candidate)) { renameSync(candidate, newSavePath); break; }
                }
              } catch {}
            }
          }
        }
      }

      // ── State folder ──────────────────────────────────────────────────────────
      // Target: statesRoot/newBase/ (folder, not a file). Migrate state files from
      // the current folder and legacy locations (matched by the OLD base).
      if (stateFolder) {
        const statesRoot = dirname(stateFolder);
        newStateFolder   = join(statesRoot, newBase);
        mkdirSync(newStateFolder, { recursive: true });
        const stateExts  = ["state", "state.auto", "state1", "state2", "state3", "state4", "state5"];
        // From the current folder: statesRoot/OldName/oldBase.stateN → newBase.stateN
        for (const ext of stateExts) {
          const src = join(stateFolder, `${oldBase}.${ext}`);
          if (stateFolder !== newStateFolder && existsSync(src)) {
            renameSync(src, join(newStateFolder, `${newBase}.${ext}`));
          }
        }
        // Legacy flat root + core subfolders: statesRoot/[core/]oldBase.stateN
        for (const ext of stateExts) {
          const src = join(statesRoot, `${oldBase}.${ext}`);
          if (existsSync(src)) renameSync(src, join(newStateFolder, `${newBase}.${ext}`));
        }
        try {
          for (const e of readdirSync(statesRoot, { withFileTypes: true })) {
            if (!e.isDirectory() || e.name === newBase) continue;
            for (const ext of stateExts) {
              const src = join(statesRoot, e.name, `${oldBase}.${ext}`);
              if (existsSync(src)) renameSync(src, join(newStateFolder, `${newBase}.${ext}`));
            }
          }
        } catch {}
      }

      return { ok: true, newRomPath, newSavePath, newStateFolder, newSecondaryRomPath };
    } catch (e: any) {
      return { ok: false, newRomPath: romPath, newSavePath, newStateFolder, newSecondaryRomPath: secondaryRomPath, error: e.message };
    }
  });
}
