// Game-folder management IPC — Switch games live one-per-folder and sync as
// a whole folder via emusync push/pull (#441), so this is the local-file
// counterpart: reveal the folder in the OS file manager, and add a file
// (e.g. a DLC .nsp) into it directly from the GUI.
import { ipcMain, shell } from "electron";
import { existsSync, copyFileSync, mkdirSync } from "fs";
import { dirname, join, basename } from "path";
import { loadServerCfg } from "./config-store";

async function romFolderFor(slug: string): Promise<string | null> {
  const { host, port, authHeaders } = loadServerCfg();
  const res = await fetch(`http://${host}:${port}/games/${slug}/device`, { headers: authHeaders, signal: AbortSignal.timeout(5000) });
  if (!res.ok) return null;
  const gd = await res.json() as { rom_path?: string };
  return gd.rom_path ? dirname(gd.rom_path) : null;
}

export function registerGameFolderIpc(): void {
  ipcMain.handle(
    "gamefolder:reveal",
    async (_event, slug: string): Promise<{ ok: boolean; error?: string }> => {
      const folder = await romFolderFor(slug);
      if (!folder || !existsSync(folder)) return { ok: false, error: "Game folder not found" };
      const err = await shell.openPath(folder);
      return err ? { ok: false, error: err } : { ok: true };
    }
  );

  ipcMain.handle(
    "gamefolder:addFile",
    async (_event, slug: string, filePath: string): Promise<{ ok: boolean; error?: string }> => {
      try {
        if (!existsSync(filePath)) return { ok: false, error: `File not found: ${filePath}` };
        const folder = await romFolderFor(slug);
        if (!folder) return { ok: false, error: "This game is not configured on this device" };
        mkdirSync(folder, { recursive: true });
        const dest = join(folder, basename(filePath));
        if (dest !== filePath) copyFileSync(filePath, dest);
        return { ok: true };
      } catch (e: any) {
        return { ok: false, error: e.message || "Add failed" };
      }
    }
  );
}
