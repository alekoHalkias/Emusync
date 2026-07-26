// Switch update/DLC file management IPC (#441). Eden has no headless install
// path for update/DLC .nsp files and its installed content lives in one
// shared NAND content store, not a per-title folder, so it can't be synced
// like a save/state. Instead this manages the not-yet-installed files
// themselves: added into a managed per-game folder, pushed to other devices
// via the same rom-transfer pipe ROMs use — tagged X-Transfer-Kind: update
// so the receiving side never overwrites the game's rom_path.
import { ipcMain } from "electron";
import { existsSync, mkdirSync, readdirSync, statSync, copyFileSync, createReadStream, basename } from "fs";
import { request as httpRequest } from "http";
import { join, homedir } from "path";
import { loadServerCfg } from "../config-store";

/** Managed folder for a game's Switch update/DLC files — mirrors
 *  cli/transfer.py's switch_updates_dir(). */
function switchUpdatesDir(slug: string): string {
  return join(homedir(), ".emusync", "switch_updates", slug);
}

export function registerUpdateIpc(): void {
  ipcMain.handle(
    "update:add",
    async (_event, slug: string, filePath: string): Promise<{ ok: boolean; error?: string }> => {
      try {
        if (!existsSync(filePath)) return { ok: false, error: `File not found: ${filePath}` };
        const destDir = switchUpdatesDir(slug);
        mkdirSync(destDir, { recursive: true });
        const dest = join(destDir, basename(filePath));
        if (dest !== filePath) copyFileSync(filePath, dest);
        return { ok: true };
      } catch (e: any) {
        return { ok: false, error: e.message || "Add failed" };
      }
    }
  );

  ipcMain.handle(
    "update:list",
    async (_event, slug: string): Promise<{ name: string; sizeBytes: number }[]> => {
      const destDir = switchUpdatesDir(slug);
      if (!existsSync(destDir)) return [];
      return readdirSync(destDir)
        .map(name => ({ name, sizeBytes: statSync(join(destDir, name)).size }))
        .sort((a, b) => a.name.localeCompare(b.name));
    }
  );

  ipcMain.handle(
    "update:push",
    async (_event, slug: string, filename: string, toDeviceId: string): Promise<{ ok: boolean; targetOnline?: boolean; error?: string }> => {
      try {
        const localPath = join(switchUpdatesDir(slug), filename);
        if (!existsSync(localPath)) return { ok: false, error: `Not in the managed folder: ${filename}` };

        const { host, port, authHeaders } = loadServerCfg();
        const fileSize = statSync(localPath).size;

        const result = await new Promise<any>((resolve, reject) => {
          const req = httpRequest(
            {
              method: "POST",
              host,
              port,
              path: `/games/${slug}/rom-transfer`,
              headers: {
                ...authHeaders,
                "Content-Type": "application/octet-stream",
                "Content-Length": fileSize,
                "X-To-Device-ID": toDeviceId,
                // Filename only — the receiving device always lands this in
                // its own managed folder, never a sender-supplied path.
                "X-Destination-Path": filename,
                "X-Filename": filename,
                "X-Transfer-Kind": "update",
              },
            },
            (res) => {
              let body = "";
              res.on("data", (chunk: Buffer) => { body += chunk.toString(); });
              res.on("end", () => {
                if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) {
                  try { resolve(JSON.parse(body)); } catch { resolve({}); }
                } else {
                  try {
                    const msg = JSON.parse(body);
                    reject(new Error(msg.detail || `Server error ${res.statusCode}`));
                  } catch {
                    reject(new Error(`Server error ${res.statusCode}`));
                  }
                }
              });
            }
          );
          req.on("error", reject);
          createReadStream(localPath).pipe(req);
        });

        return { ok: true, targetOnline: result.target_online };
      } catch (e: any) {
        return { ok: false, error: e.message || "Push failed" };
      }
    }
  );
}
