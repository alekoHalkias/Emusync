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
import { join } from "path";
import { homedir } from "os";
import { loadServerCfg } from "../config-store";

/** Managed folder for a game's Switch update/DLC files — mirrors
 *  cli/transfer.py's switch_updates_dir(). */
function switchUpdatesDir(slug: string): string {
  return join(homedir(), ".emusync", "switch_updates", slug);
}

/** Every update/DLC file available for `slug` on this device, basename ->
 *  absolute path — merges the managed folder (explicitly added files) with
 *  files auto-detected next to the base ROM at import time (#441). A managed
 *  copy wins on a basename collision, since it was an explicit user action.
 *  Mirrors cli/update.py's _resolve_update_files(). */
async function resolveUpdateFiles(slug: string): Promise<Map<string, string>> {
  const files = new Map<string, string>();
  try {
    const { host, port, authHeaders } = loadServerCfg();
    const res = await fetch(`http://${host}:${port}/games/${slug}/device`, { headers: authHeaders, signal: AbortSignal.timeout(5000) });
    if (res.ok) {
      const gd = await res.json() as { update_paths?: string[] };
      for (const path of gd.update_paths ?? []) {
        if (existsSync(path) && statSync(path).isFile()) files.set(basename(path), path);
      }
    }
  } catch { /* server unreachable — managed folder alone still works */ }

  const destDir = switchUpdatesDir(slug);
  if (existsSync(destDir)) {
    for (const name of readdirSync(destDir)) {
      const path = join(destDir, name);
      if (statSync(path).isFile()) files.set(name, path);
    }
  }
  return files;
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
      const files = await resolveUpdateFiles(slug);
      return [...files.entries()]
        .map(([name, path]) => ({ name, sizeBytes: statSync(path).size }))
        .sort((a, b) => a.name.localeCompare(b.name));
    }
  );

  ipcMain.handle(
    "update:push",
    async (_event, slug: string, filename: string, toDeviceId: string): Promise<{ ok: boolean; targetOnline?: boolean; error?: string }> => {
      try {
        const files = await resolveUpdateFiles(slug);
        const localPath = files.get(filename);
        if (!localPath) return { ok: false, error: `'${filename}' isn't available for this game on this device` };

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
