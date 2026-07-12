// SteamGridDB shared-key handling (issue #322) — the key is entered once from
// any device (#398) and shared to every device via the EmuSync server, since
// SteamGridDB has no OAuth/programmatic flow for a third-party app to obtain
// a per-user key (confirmed: every integration — Steam ROM Manager, RomM,
// SteamTinkerLaunch — requires manually pasting a key obtained from
// steamgriddb.com/profile/preferences/api).
import { ipcMain, shell } from "electron";
import { loadServerCfg } from "./config-store";

const STEAMGRIDDB_KEY_URL = "https://www.steamgriddb.com/profile/preferences/api";

// Cached for this process's lifetime — art:get calls this on every cache miss,
// and the key rarely changes, so there's no need to hit the server every
// time. A key changed on the server takes effect here on next app restart.
let cachedKey: string | null | undefined; // undefined = not yet fetched this run

export async function getSteamGridDbKey(): Promise<string | null> {
  if (cachedKey !== undefined) return cachedKey;
  try {
    const { host, port, authHeaders } = loadServerCfg();
    const res = await fetch(`http://${host}:${port}/settings/steamgriddb-key`, {
      headers: authHeaders,
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) return null;
    const body = await res.json() as { api_key: string | null };
    cachedKey = body.api_key || null;
    return cachedKey;
  } catch {
    return null;
  }
}

export function registerSteamGridDbIpc(): void {
  ipcMain.handle("steamgriddb:getKey", (): Promise<string | null> => getSteamGridDbKey());

  ipcMain.handle("steamgriddb:setKey", async (_event, key: string): Promise<{ ok: boolean; error?: string }> => {
    try {
      const { host, port, authHeaders } = loadServerCfg();
      const res = await fetch(`http://${host}:${port}/settings/steamgriddb-key`, {
        method: "PUT",
        headers: { ...authHeaders, "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: key }),
        signal: AbortSignal.timeout(5000),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: res.statusText }));
        return { ok: false, error: (body as any).detail ?? res.statusText };
      }
      cachedKey = key || null; // refresh this process's own cache immediately
      return { ok: true };
    } catch (e: any) {
      return { ok: false, error: e.message || "Failed to save key" };
    }
  });

  ipcMain.handle("steamgriddb:openKeyPage", async (): Promise<void> => {
    await shell.openExternal(STEAMGRIDDB_KEY_URL);
  });
}
