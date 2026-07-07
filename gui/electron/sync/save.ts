// Save-file push/pull IPC.
import { ipcMain } from "electron";
import { existsSync, readFileSync, writeFileSync, mkdirSync } from "fs";
import { dirname } from "path";
import { loadServerCfg } from "../config-store";

export function registerSaveIpc(): void {
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
}
