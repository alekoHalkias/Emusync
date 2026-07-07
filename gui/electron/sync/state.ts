// Save-state folder push/pull IPC (tar.gz archives, one folder per game).
import { ipcMain } from "electron";
import { spawnSync } from "child_process";
import { existsSync, mkdirSync, readdirSync, unlinkSync, renameSync } from "fs";
import { join } from "path";
import { loadServerCfg } from "../config-store";

export function registerStateIpc(): void {
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
}
