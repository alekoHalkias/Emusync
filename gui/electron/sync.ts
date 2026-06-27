// Save / state / ROM sync IPC — the handlers that move bytes between this
// device and the Python server.
import { ipcMain } from "electron";
import { spawnSync } from "child_process";
import { existsSync, readFileSync, writeFileSync, mkdirSync, readdirSync, unlinkSync, rmdirSync, renameSync, statSync, statfsSync, copyFileSync, createReadStream } from "fs";
import { createHash } from "crypto";
import { request as httpRequest } from "http";
import { join, dirname, basename, resolve as resolvePath } from "path";
import { parse as parseTOML } from "smol-toml";
import { CONFIG_PATH } from "./runtime";
import { loadServerCfg } from "./config-store";

export function registerSyncIpc(): void {
  // ── save sync ───────────────────────────────────────────────────────────────

  ipcMain.handle("save:push", async (_event, slug: string, savePath: string): Promise<{ ok: boolean; error?: string }> => {
    try {
      if (!existsSync(savePath)) return { ok: false, error: "Save file not found" };
      const { host, port, authHeaders } = loadServerCfg();
      const data = readFileSync(savePath);
      const res = await fetch(`http://${host}:${port}/games/${slug}/save`, {
        method: "POST",
        headers: { ...authHeaders, "Content-Type": "application/octet-stream" },
        body: data,
        signal: AbortSignal.timeout(30000),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: res.statusText }));
        return { ok: false, error: (body as any).detail ?? res.statusText };
      }
      return { ok: true };
    } catch (e: any) {
      return { ok: false, error: e.message || "Push failed" };
    }
  });

  ipcMain.handle("save:pull", async (_event, slug: string, savePath: string): Promise<{ ok: boolean; pulled: boolean; error?: string }> => {
    try {
      const { host, port, authHeaders } = loadServerCfg();
      const res = await fetch(`http://${host}:${port}/games/${slug}/save`, {
        headers: authHeaders,
        signal: AbortSignal.timeout(30000),
      });
      if (res.status === 204) return { ok: true, pulled: false };
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: res.statusText }));
        return { ok: false, pulled: false, error: (body as any).detail ?? res.statusText };
      }
      const buf = Buffer.from(await res.arrayBuffer());
      if (existsSync(savePath)) {
        writeFileSync(`${savePath}.bak`, readFileSync(savePath));
      }
      mkdirSync(dirname(savePath), { recursive: true });
      writeFileSync(savePath, buf);
      return { ok: true, pulled: true };
    } catch (e: any) {
      return { ok: false, pulled: false, error: e.message || "Pull failed" };
    }
  });

  // ── state sync ────────────────────────────────────────────────────────────────

  ipcMain.handle("state:push", async (_event, slug: string, statePath: string): Promise<{ ok: boolean; error?: string }> => {
    try {
      // statePath is the state FOLDER. Pack all files inside it into a tar.gz
      // archive so that every state slot (game.state, game.state1, …) is synced.
      if (!existsSync(statePath)) return { ok: false, error: "State folder not found" };
      // Exclude .bak backups (kept by state:pull) so they don't propagate to peers.
      const tarResult = spawnSync("tar", ["-czf", "-", "-C", statePath, "--exclude=*.bak", "."], {
        maxBuffer: 200 * 1024 * 1024,
      });
      if (tarResult.error || tarResult.status !== 0) {
        return { ok: false, error: `Failed to compress state folder: ${tarResult.stderr?.toString().trim() ?? ""}` };
      }
      const data = tarResult.stdout as Buffer;
      if (!data || data.length === 0) return { ok: false, error: "No state files to push" };
      const { host, port, authHeaders } = loadServerCfg();
      const res = await fetch(`http://${host}:${port}/games/${slug}/state`, {
        method: "POST",
        headers: { ...authHeaders, "Content-Type": "application/octet-stream" },
        body: data,
        signal: AbortSignal.timeout(60000),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: res.statusText }));
        return { ok: false, error: (body as any).detail ?? res.statusText };
      }
      return { ok: true };
    } catch (e: any) {
      return { ok: false, error: e.message || "Push failed" };
    }
  });

  ipcMain.handle("state:pull", async (_event, slug: string, statePath: string): Promise<{ ok: boolean; pulled: boolean; error?: string }> => {
    try {
      const { host, port, authHeaders } = loadServerCfg();
      const res = await fetch(`http://${host}:${port}/games/${slug}/state`, {
        headers: authHeaders,
        signal: AbortSignal.timeout(60000),
      });
      if (res.status === 204) return { ok: true, pulled: false };
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: res.statusText }));
        return { ok: false, pulled: false, error: (body as any).detail ?? res.statusText };
      }
      const buf = Buffer.from(await res.arrayBuffer());
      // Ensure the state folder exists and back up any existing files. The .bak
      // backups are RETAINED on success so an overwrite is recoverable (a state
      // pull must not be destructive); unlink any prior .bak first so only one
      // generation is kept and renameSync can't fail on Windows.
      mkdirSync(statePath, { recursive: true });
      const existing = readdirSync(statePath).filter(f => !f.endsWith(".bak"));
      for (const f of existing) {
        const bak = join(statePath, f + ".bak");
        try { if (existsSync(bak)) unlinkSync(bak); } catch {}
        try { renameSync(join(statePath, f), bak); } catch {}
      }
      // Extract the tar.gz archive into the state folder
      const extractResult = spawnSync("tar", ["-xzf", "-", "-C", statePath], {
        input: buf,
        maxBuffer: 200 * 1024 * 1024,
      });
      if (extractResult.error || extractResult.status !== 0) {
        // Restore backups on failure
        for (const f of existing) {
          const bak = join(statePath, f + ".bak");
          if (existsSync(bak)) try { renameSync(bak, join(statePath, f)); } catch {}
        }
        return { ok: false, pulled: false, error: "Failed to extract state archive" };
      }
      // Backups are intentionally kept on success (see comment above).
      return { ok: true, pulled: true };
    } catch (e: any) {
      return { ok: false, pulled: false, error: e.message || "Pull failed" };
    }
  });

  // ── rom push ──────────────────────────────────────────────────────────────────

  ipcMain.handle(
    "rom:push",
    async (_event, slug: string, toDeviceId: string, consoleName: string): Promise<{ ok: boolean; targetOnline?: boolean; error?: string }> => {
      try {
        // Read server config from TOML
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

        // 1. Get local game device config to find rom_path
        const gdRes = await fetch(`http://${host}:${port}/games/${slug}/device`, { headers: authHeaders, signal: AbortSignal.timeout(5000) });
        if (!gdRes.ok) return { ok: false, error: "This game is not configured on this device" };
        const gd = await gdRes.json() as any;
        if (!gd.rom_path) return { ok: false, error: "No ROM path configured for this game" };
        if (!existsSync(gd.rom_path)) return { ok: false, error: `ROM file not found: ${gd.rom_path}` };

        // 2. Get target device consoles to find its ROM folder for this console
        const consolesRes = await fetch(`http://${host}:${port}/devices/${toDeviceId}/consoles`, { headers: authHeaders, signal: AbortSignal.timeout(5000) });
        if (!consolesRes.ok) return { ok: false, error: "Could not read target device configuration" };
        const consoles = await consolesRes.json() as Array<{ console_name: string; device_game_folder: string }>;

        const match = consoles.find(c => c.console_name === consoleName);
        if (!match?.device_game_folder) {
          return { ok: false, error: `${consoleName} is not configured on the target device yet` };
        }

        const romFilename = basename(gd.rom_path);
        const destinationPath = join(match.device_game_folder, romFilename);
        const fileSize = statSync(gd.rom_path).size;

        // 3. Stream ROM file to server via http.request (fetch can't stream a local file reliably)
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
                "X-Destination-Path": destinationPath,
                "X-Filename": romFilename,
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
          createReadStream(gd.rom_path).pipe(req);
        });

        return { ok: true, targetOnline: result.target_online };
      } catch (e: any) {
        return { ok: false, error: e.message || "Push failed" };
      }
    }
  );

  // ── network ROM localize / delocalize (issue #255) ──────────────────────────
  // Copy a network-sourced ROM onto local disk for offline play, and remove it.
  // The NAS master is never modified or deleted.

  ipcMain.handle(
    "rom:localize",
    async (_event, slug: string, destFolder?: string): Promise<{ ok: boolean; localPath?: string; error?: string }> => {
      try {
        const { host, port, authHeaders } = loadServerCfg();
        const gdRes = await fetch(`http://${host}:${port}/games/${slug}/device`, { headers: authHeaders, signal: AbortSignal.timeout(5000) });
        if (!gdRes.ok) return { ok: false, error: "Game is not configured on this device" };
        const gd = await gdRes.json() as any;
        if (gd.rom_source !== "network") return { ok: false, error: "Not a network-sourced ROM" };

        const networkPath = gd.rom_path as string;
        if (!networkPath || !existsSync(networkPath)) {
          return { ok: false, error: "Network ROM is unreachable (is the share mounted?)" };
        }

        // Destination precedence: an already-stored local path → an explicit
        // destFolder (from a picker) → the console's configured local folder.
        const rel = (gd.rom_rel_path as string) || basename(networkPath);
        let localPath = (gd.local_rom_path as string) || "";
        let learnedFolder = "";   // a folder we should remember on the console
        if (!localPath) {
          let folder = destFolder || "";
          if (!folder) folder = await consoleLocalFolder(host, port, authHeaders, slug);
          if (!folder) return { ok: false, error: "No local destination set for this console — choose a folder." };
          if (destFolder) learnedFolder = destFolder;  // teach the console this folder
          localPath = join(folder, ...rel.split("/"));
        }
        if (resolvePath(localPath) === resolvePath(networkPath)) {
          return { ok: false, error: "Local destination equals the network master" };
        }
        mkdirSync(dirname(localPath), { recursive: true });

        // Free-space precheck so a big console can't half-fill the disk.
        const size = statSync(networkPath).size;
        const fs = statfsSync(dirname(localPath));
        const free = Number(fs.bavail) * Number(fs.bsize);
        if (free < size) {
          return { ok: false, error: `Not enough free space: need ${size} bytes, ${free} available` };
        }

        // Atomic: copy to .part, hash, then rename into place.
        const tmp = localPath + ".part";
        try {
          copyFileSync(networkPath, tmp);
          const hash = await sha256OfFile(tmp);
          renameSync(tmp, localPath);
          // Remember a manually-picked folder on the console so the next game of
          // this console localizes without re-prompting (issue #255).
          const updated = { ...gd, local_rom_path: localPath, rom_sha256: hash,
            ...(learnedFolder ? { device_local_folder: learnedFolder } : {}) };
          const putRes = await fetch(`http://${host}:${port}/games/${slug}/device`, {
            method: "PUT",
            headers: { ...authHeaders, "Content-Type": "application/json" },
            body: JSON.stringify(updated),
          });
          if (!putRes.ok) return { ok: false, error: "Copied, but failed to update server config" };
          return { ok: true, localPath };
        } finally {
          if (existsSync(tmp)) { try { unlinkSync(tmp); } catch { /* best effort */ } }
        }
      } catch (e: any) {
        return { ok: false, error: e.message || "Localize failed" };
      }
    }
  );

  ipcMain.handle(
    "rom:delocalize",
    async (_event, slug: string): Promise<{ ok: boolean; error?: string }> => {
      try {
        const { host, port, authHeaders } = loadServerCfg();
        const gdRes = await fetch(`http://${host}:${port}/games/${slug}/device`, { headers: authHeaders, signal: AbortSignal.timeout(5000) });
        if (!gdRes.ok) return { ok: false, error: "Game is not configured on this device" };
        const gd = await gdRes.json() as any;
        const localPath = (gd.local_rom_path as string) || "";
        if (!localPath) return { ok: false, error: "No local copy to remove" };
        // Guard: never delete the NAS master.
        if (gd.rom_path && resolvePath(localPath) === resolvePath(gd.rom_path)) {
          return { ok: false, error: "Refusing to delete the network master" };
        }
        if (existsSync(localPath)) unlinkSync(localPath);
        // Remove now-empty per-game folders left behind, walking up to (but not
        // including) the console's local root. rmdirSync throws on a non-empty
        // dir, so a folder still holding other ROMs is never touched (#255).
        try {
          const root = await consoleLocalFolder(host, port, authHeaders, slug);
          const stop = root ? resolvePath(root) : "";
          // Without a known root, only the immediate parent is cleaned, so we
          // never walk up an unbounded chain of coincidentally-empty dirs.
          let remaining = stop ? Infinity : 1;
          let dir = dirname(localPath);
          while (remaining-- > 0 && dir && resolvePath(dir) !== stop && dir !== dirname(dir)) {
            rmdirSync(dir);            // throws if non-empty → caught below, loop ends
            dir = dirname(dir);
          }
        } catch { /* hit a non-empty dir or the root — nothing more to clean */ }
        const updated = { ...gd, local_rom_path: "", rom_sha256: "" };
        const putRes = await fetch(`http://${host}:${port}/games/${slug}/device`, {
          method: "PUT",
          headers: { ...authHeaders, "Content-Type": "application/json" },
          body: JSON.stringify(updated),
        });
        if (!putRes.ok) return { ok: false, error: "Removed copy, but failed to update server config" };
        return { ok: true };
      } catch (e: any) {
        return { ok: false, error: e.message || "Delocalize failed" };
      }
    }
  );
}

// Look up this game's console, then its configured local-copy folder on this
// device — the destination chosen during a network import (issue #255).
async function consoleLocalFolder(
  host: string, port: number, authHeaders: Record<string, string>, slug: string,
): Promise<string> {
  try {
    const gameRes = await fetch(`http://${host}:${port}/games/${slug}`, { headers: authHeaders, signal: AbortSignal.timeout(5000) });
    if (!gameRes.ok) return "";
    const game = await gameRes.json() as { console?: string };
    const whoamiRes = await fetch(`http://${host}:${port}/whoami`, { headers: authHeaders, signal: AbortSignal.timeout(5000) });
    if (!whoamiRes.ok) return "";
    const { device_id } = await whoamiRes.json() as { device_id: string };
    const consolesRes = await fetch(`http://${host}:${port}/devices/${device_id}/consoles`, { headers: authHeaders, signal: AbortSignal.timeout(5000) });
    if (!consolesRes.ok) return "";
    const consoles = await consolesRes.json() as Array<{ console_name: string; device_local_folder?: string }>;
    // A console can have several rows (e.g. a prior local import + this network
    // one); prefer whichever row actually has a local folder configured.
    const matches = consoles.filter(c => c.console_name === game.console);
    return matches.find(c => c.device_local_folder)?.device_local_folder
      || matches[0]?.device_local_folder || "";
  } catch {
    return "";
  }
}

function sha256OfFile(path: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const h = createHash("sha256");
    const s = createReadStream(path);
    s.on("error", reject);
    s.on("data", (d) => h.update(d));
    s.on("end", () => resolve(h.digest("hex")));
  });
}
