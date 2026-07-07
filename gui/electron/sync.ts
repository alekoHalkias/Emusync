// Save / state / ROM sync IPC — the handlers that move bytes between this
// device and the Python server.
import { ipcMain } from "electron";
import { spawnSync } from "child_process";
import { existsSync, readFileSync, writeFileSync, mkdirSync, readdirSync, unlinkSync, rmdirSync, renameSync, statSync, statfsSync, copyFileSync, createReadStream } from "fs";
import { createHash } from "crypto";
import { request as httpRequest } from "http";
import { join, dirname, basename, resolve as resolvePath } from "path";
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

  // ── console-scoped shared memory card (issue #295) ──────────────────────────
  // One card per console (PS2), shared across every game on that console. Pull
  // is used by the import wizard to bring a newly-imported shared-layout
  // console's card in from the server (issue #316); push backs the manual
  // "Push memory card" button in GameConfig (issue #319) — the automatic push
  // only happens post-launch via emusync run, with no on-demand equivalent
  // until now (e.g. for a card edited/copied in outside of a play session).

  ipcMain.handle("memcard:push", async (_event, consoleKey: string, cardPath: string): Promise<{ ok: boolean; error?: string }> => {
    try {
      if (!existsSync(cardPath)) return { ok: false, error: "Memory card file not found" };
      const { host, port, authHeaders } = loadServerCfg();
      let data: Buffer;
      if (statSync(cardPath).isDirectory()) {
        // Folder-based memcard (PCSX2 .ps2 dir) — pack as plain tar, matching
        // the Python memcard_bytes() serialisation so the server hash is stable.
        const tarResult = spawnSync("tar", ["-cf", "-", "--exclude=*.bak", "-C", cardPath, "."], {
          maxBuffer: 512 * 1024 * 1024,
        });
        if (tarResult.error || tarResult.status !== 0) {
          return { ok: false, error: `Failed to pack memory card folder: ${tarResult.stderr?.toString().trim() ?? ""}` };
        }
        data = tarResult.stdout as Buffer;
        if (!data || data.length === 0) return { ok: false, error: "Memory card folder is empty" };
      } else {
        data = readFileSync(cardPath);
      }
      const res = await fetch(`http://${host}:${port}/consoles/${consoleKey}/memcard`, {
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

  ipcMain.handle("memcard:pull", async (_event, consoleKey: string, cardPath: string): Promise<{ ok: boolean; pulled: boolean; error?: string }> => {
    try {
      const { host, port, authHeaders } = loadServerCfg();
      const res = await fetch(`http://${host}:${port}/consoles/${consoleKey}/memcard`, {
        headers: authHeaders,
        signal: AbortSignal.timeout(30000),
      });
      if (res.status === 204) return { ok: true, pulled: false };
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: res.statusText }));
        return { ok: false, pulled: false, error: (body as any).detail ?? res.statusText };
      }
      const buf = Buffer.from(await res.arrayBuffer());

      // Write to a temp file so we can probe it with tar before deciding where it goes.
      const tmpPath = `${cardPath}.pull.tmp`;
      writeFileSync(tmpPath, buf);
      try {
        const probe = spawnSync("tar", ["-tf", tmpPath], { stdio: "pipe" });
        if (probe.status === 0) {
          // Folder-based memcard — received a tar archive. Back up the whole
          // existing memcard (file or folder) as a single <name>.bak sibling.
          const bakPath = `${cardPath}.bak`;
          if (existsSync(cardPath)) {
            if (existsSync(bakPath)) spawnSync("rm", ["-rf", bakPath]);
            if (statSync(cardPath).isDirectory()) {
              spawnSync("cp", ["-r", cardPath, bakPath]);
            } else {
              writeFileSync(bakPath, readFileSync(cardPath));
              unlinkSync(cardPath);
            }
          }
          mkdirSync(cardPath, { recursive: true });
          const extract = spawnSync("tar", ["-xf", tmpPath, "-C", cardPath]);
          if (extract.status !== 0) {
            return { ok: false, pulled: false, error: `Failed to extract memory card: ${extract.stderr?.toString().trim() ?? ""}` };
          }
        } else {
          // File-based memcard — write raw bytes directly.
          if (existsSync(cardPath)) {
            if (statSync(cardPath).isFile()) {
              writeFileSync(`${cardPath}.bak`, readFileSync(cardPath));
            }
            // If it's a directory we leave it alone and just write the file alongside it.
          }
          mkdirSync(dirname(cardPath), { recursive: true });
          renameSync(tmpPath, cardPath);
          return { ok: true, pulled: true };
        }
      } finally {
        try { if (existsSync(tmpPath)) unlinkSync(tmpPath); } catch {}
      }
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
        const { host, port, authHeaders } = loadServerCfg();

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

  // ── tiered game delete (issue #343) ─────────────────────────────────────────
  // A bare file delete for the two delete-tier cases that have no cleanup logic
  // of their own: a local-source ROM (delocalize already handles a network
  // ROM's localized copy, with empty-dir cleanup) and a network master.

  ipcMain.handle(
    "rom:deleteFile",
    async (_event, absolutePath: string): Promise<{ ok: boolean; error?: string }> => {
      try {
        if (absolutePath && existsSync(absolutePath)) unlinkSync(absolutePath);
        return { ok: true };
      } catch (e: any) {
        return { ok: false, error: e.message || "Delete failed" };
      }
    }
  );

  // ── network ROM upload-to-master (issue #270) ───────────────────────────────
  // Copy a local-only ROM UP to the network share so the share becomes the
  // canonical master. Mirror of rom:localize in reverse. Never overwrites an
  // existing master (skip → treat it as authoritative). Used by the import wizard
  // when a game is found locally but not yet on the network drive.
  ipcMain.handle(
    "rom:uploadMaster",
    async (_event, localPath: string, networkPath: string): Promise<{ ok: boolean; sha256?: string; skipped?: boolean; error?: string }> => {
      try {
        if (!localPath || !existsSync(localPath)) return { ok: false, error: `Local ROM not found: ${localPath}` };
        if (!networkPath) return { ok: false, error: "No network destination given" };
        if (resolvePath(localPath) === resolvePath(networkPath)) {
          return { ok: false, error: "Network destination equals the local source" };
        }
        // A master already on the share is authoritative — never clobber it.
        if (existsSync(networkPath)) {
          return { ok: true, skipped: true, sha256: await sha256OfFile(networkPath) };
        }
        const parent = dirname(networkPath);
        mkdirSync(parent, { recursive: true });
        // Free-space precheck on the share so a big console can't half-fill it.
        const size = statSync(localPath).size;
        const fs = statfsSync(parent);
        const free = Number(fs.bavail) * Number(fs.bsize);
        if (free < size) {
          return { ok: false, error: `Not enough free space on the share: need ${size} bytes, ${free} available` };
        }
        // Atomic: copy to .part on the share, verify, then rename into place.
        const tmp = networkPath + ".part";
        try {
          copyFileSync(localPath, tmp);
          const hash = await sha256OfFile(tmp);
          if (await sha256OfFile(localPath) !== hash) {
            return { ok: false, error: "Upload verification failed (hash mismatch)" };
          }
          renameSync(tmp, networkPath);
          return { ok: true, skipped: false, sha256: hash };
        } finally {
          if (existsSync(tmp)) { try { unlinkSync(tmp); } catch { /* best effort */ } }
        }
      } catch (e: any) {
        return { ok: false, error: e.message || "Upload failed" };
      }
    }
  );

  // ── play-time cross-device network setup (issue #270) ───────────────────────
  // For a game configured on a network share by another device, point THIS
  // device at the same share (its own mount root), verify the ROM is reachable,
  // and create a network-source config here so it can be played. Save/state paths
  // are derived from this device's console folders when configured; run.py's
  // post-launch auto-detection refines them on first play.
  ipcMain.handle(
    "rom:setupNetworkPlay",
    async (_event, slug: string, mountRoot: string): Promise<{ ok: boolean; romPath?: string; error?: string }> => {
      try {
        if (!mountRoot) return { ok: false, error: "No mount root selected" };
        const { host, port, authHeaders } = loadServerCfg();
        const srcRes = await fetch(`http://${host}:${port}/games/${slug}/network-source`, { headers: authHeaders, signal: AbortSignal.timeout(5000) });
        if (!srcRes.ok) return { ok: false, error: "No network-drive config found for this game on any device" };
        const src = await srcRes.json() as {
          console: string; rom_path: string; rom_rel_path: string;
          launch_command: string; save_path: string; state_path: string;
        };

        const rel = src.rom_rel_path;
        // Reject traversal / absolute / drive-qualified rel-paths before joining.
        const segs = rel.replace(/\\/g, "/").split("/").filter(Boolean);
        if (!rel || rel.includes(":") || segs.some(s => s === "..")) {
          return { ok: false, error: `Unsafe ROM path from source device: ${rel}` };
        }
        const romPath = join(mountRoot, ...segs);
        if (!existsSync(romPath)) {
          return { ok: false, error: `ROM not found at ${romPath}. Check that the share is mounted and the root is correct.` };
        }

        // Derive this device's save/state paths from its console folders, reusing
        // the source's per-game tail (GameName/GameName.srm and GameName/).
        const folders = await consoleSaveStateFolders(host, port, authHeaders, src.console);
        const saveTail = tailSegments(src.save_path, 2);
        const stateTail = tailSegments(src.state_path, 1);
        const savePath = folders.saveFolder && saveTail.length
          ? join(folders.saveFolder, ...saveTail)
          : src.save_path;
        const statePath = src.state_path
          ? (folders.stateFolder && stateTail.length ? join(folders.stateFolder, ...stateTail) : src.state_path)
          : "";

        const launchCommand = src.rom_path
          ? src.launch_command.split(src.rom_path).join(romPath)
          : src.launch_command;

        const updated = {
          rom_path: romPath,
          save_path: savePath,
          state_path: statePath,
          launch_command: launchCommand,
          rom_folder_path: dirname(romPath),
          rom_source: "network",
          rom_rel_path: rel,
          local_rom_path: "",
          device_network_folder: mountRoot,
        };
        const putRes = await fetch(`http://${host}:${port}/games/${slug}/device`, {
          method: "PUT",
          headers: { ...authHeaders, "Content-Type": "application/json" },
          body: JSON.stringify(updated),
        });
        if (!putRes.ok) return { ok: false, error: "Verified the ROM, but failed to save the config" };
        return { ok: true, romPath };
      } catch (e: any) {
        return { ok: false, error: e.message || "Network play setup failed" };
      }
    }
  );

  // ── local backup recovery (issue #285) ──────────────────────────────────────
  // Surface the on-disk `.bak` losers (a save's `<save>.bak`, a state folder's
  // `*.bak`) for the recovery view, and restore one back into place. These are
  // copies that may never have reached the server (e.g. the loser of an offline
  // conflict), so they're only recoverable locally.

  ipcMain.handle(
    "recovery:listLocalBackups",
    async (_event, savePath: string, stateFolder: string): Promise<{ saves: LocalBak[]; states: LocalBak[] }> => {
      const saves: LocalBak[] = [];
      const states: LocalBak[] = [];
      // Every fs touch is guarded so a dead network mount yields an empty list
      // instead of throwing/hanging; no recursive traversal.
      if (savePath) {
        const bak = `${savePath}.bak`;
        try {
          if (existsSync(bak)) {
            const st = statSync(bak);
            saves.push({ path: bak, kind: "save", size: st.size, mtime: st.mtime.toISOString(), fileName: basename(bak) });
          }
        } catch { /* unreachable path → skip */ }
      }
      if (stateFolder) {
        try {
          for (const f of readdirSync(stateFolder)) {
            if (!f.endsWith(".bak")) continue;
            try {
              const p = join(stateFolder, f);
              const st = statSync(p);
              states.push({ path: p, kind: "state", size: st.size, mtime: st.mtime.toISOString(), fileName: f });
            } catch { /* skip this entry */ }
          }
        } catch { /* unreachable folder → skip */ }
      }
      return { saves, states };
    }
  );

  ipcMain.handle(
    "recovery:restoreLocalBackup",
    async (_event, bakPath: string, targetPath: string): Promise<{ ok: boolean; error?: string }> => {
      try {
        if (!bakPath.endsWith(".bak")) return { ok: false, error: "Not a .bak file" };
        if (!existsSync(bakPath)) return { ok: false, error: "Backup file no longer exists" };
        if (!targetPath) return { ok: false, error: "No restore target given" };
        // Read the backup bytes BEFORE writing anything: for a save the backup is
        // `<target>.bak`, so writing the target via a temp must not race the source.
        const data = readFileSync(bakPath);
        mkdirSync(dirname(targetPath), { recursive: true });
        // Atomic + Windows-safe: write to .part, unlink any stale temp, rename.
        const tmp = `${targetPath}.restore.part`;
        try { if (existsSync(tmp)) unlinkSync(tmp); } catch {}
        writeFileSync(tmp, data);
        try { if (existsSync(targetPath)) unlinkSync(targetPath); } catch {}
        renameSync(tmp, targetPath);
        return { ok: true };
      } catch (e: any) {
        return { ok: false, error: e.message || "Restore failed" };
      }
    }
  );
}

/** A `.bak` loser found on local disk (issue #285). */
interface LocalBak {
  path: string;
  kind: "save" | "state";
  size: number;
  mtime: string;
  fileName: string;
}

/** Last `n` path segments of `p` (splitting on / or \), for rebasing a path. */
function tailSegments(p: string, n: number): string[] {
  if (!p) return [];
  const segs = p.replace(/\\/g, "/").split("/").filter(Boolean);
  return segs.slice(Math.max(0, segs.length - n));
}

// This device's configured save/state folders for a console (set during import),
// used to place a cross-device network game's saves/states locally (issue #270).
async function consoleSaveStateFolders(
  host: string, port: number, authHeaders: Record<string, string>, consoleName: string,
): Promise<{ saveFolder: string; stateFolder: string }> {
  try {
    const whoamiRes = await fetch(`http://${host}:${port}/whoami`, { headers: authHeaders, signal: AbortSignal.timeout(5000) });
    if (!whoamiRes.ok) return { saveFolder: "", stateFolder: "" };
    const { device_id } = await whoamiRes.json() as { device_id: string };
    const consolesRes = await fetch(`http://${host}:${port}/devices/${device_id}/consoles`, { headers: authHeaders, signal: AbortSignal.timeout(5000) });
    if (!consolesRes.ok) return { saveFolder: "", stateFolder: "" };
    const consoles = await consolesRes.json() as Array<{ console_name: string; device_save_folder?: string; device_state_folder?: string }>;
    const matches = consoles.filter(c => c.console_name === consoleName);
    return {
      saveFolder: matches.find(c => c.device_save_folder)?.device_save_folder || "",
      stateFolder: matches.find(c => c.device_state_folder)?.device_state_folder || "",
    };
  } catch {
    return { saveFolder: "", stateFolder: "" };
  }
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
