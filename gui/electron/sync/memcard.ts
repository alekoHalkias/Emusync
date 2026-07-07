// Console-scoped shared memory card push/pull IPC (issue #295).
// One card per console (PS2), shared across every game on that console. Pull
// is used by the import wizard to bring a newly-imported shared-layout
// console's card in from the server (issue #316); push backs the manual
// "Push memory card" button in GameConfig (issue #319) — the automatic push
// only happens post-launch via emusync run, with no on-demand equivalent
// until now (e.g. for a card edited/copied in outside of a play session).
import { ipcMain } from "electron";
import { spawnSync } from "child_process";
import { existsSync, readFileSync, writeFileSync, mkdirSync, unlinkSync, statSync, renameSync } from "fs";
import { dirname } from "path";
import { loadServerCfg } from "../config-store";

export function registerMemcardIpc(): void {
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
}
