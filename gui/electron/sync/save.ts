// Save-file push/pull IPC. Wii/Switch saves are a whole NAND folder, not a
// single file (#431/#419) — mirrors the folder-vs-file branching already in
// memcard.ts (plain tar, matching Python's memcard_bytes()/_write_memcard()),
// which the manual GUI push/pull buttons here never picked up.
import { ipcMain } from "electron";
import { spawnSync } from "child_process";
import { existsSync, readFileSync, writeFileSync, mkdirSync, unlinkSync, statSync, renameSync } from "fs";
import { dirname } from "path";
import { loadServerCfg } from "../config-store";

export function registerSaveIpc(): void {
  ipcMain.handle("save:push", async (_event, slug: string, savePath: string): Promise<{ ok: boolean; error?: string }> => {
    try {
      if (!existsSync(savePath)) return { ok: false, error: "Save file not found" };
      const { host, port, authHeaders } = loadServerCfg();
      let data: Buffer;
      if (statSync(savePath).isDirectory()) {
        const tarResult = spawnSync("tar", ["-cf", "-", "--exclude=*.bak", "-C", savePath, "."], {
          maxBuffer: 512 * 1024 * 1024,
        });
        if (tarResult.error || tarResult.status !== 0) {
          return { ok: false, error: `Failed to pack save folder: ${tarResult.stderr?.toString().trim() ?? ""}` };
        }
        data = tarResult.stdout as Buffer;
        if (!data || data.length === 0) return { ok: false, error: "Save folder is empty" };
      } else {
        data = readFileSync(savePath);
      }
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

      // Write to a temp file so we can probe it with tar before deciding where it goes.
      const tmpPath = `${savePath}.pull.tmp`;
      writeFileSync(tmpPath, buf);
      try {
        const probe = spawnSync("tar", ["-tf", tmpPath], { stdio: "pipe" });
        if (probe.status === 0) {
          // Folder-based save (Wii/Switch NAND folder) — received a tar archive.
          const bakPath = `${savePath}.bak`;
          if (existsSync(savePath)) {
            if (existsSync(bakPath)) spawnSync("rm", ["-rf", bakPath]);
            if (statSync(savePath).isDirectory()) {
              spawnSync("cp", ["-r", savePath, bakPath]);
            } else {
              writeFileSync(bakPath, readFileSync(savePath));
              unlinkSync(savePath);
            }
          }
          mkdirSync(savePath, { recursive: true });
          const extract = spawnSync("tar", ["-xf", tmpPath, "-C", savePath]);
          if (extract.status !== 0) {
            return { ok: false, pulled: false, error: `Failed to extract save: ${extract.stderr?.toString().trim() ?? ""}` };
          }
        } else {
          // File-based save — write raw bytes directly.
          if (existsSync(savePath) && statSync(savePath).isFile()) {
            writeFileSync(`${savePath}.bak`, readFileSync(savePath));
          }
          mkdirSync(dirname(savePath), { recursive: true });
          renameSync(tmpPath, savePath);
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
}
