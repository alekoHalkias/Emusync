/** Thin wrapper around the EmuSync Python REST API. */

export type GameDeviceConfig = {
  rom_path: string;
  save_path: string;
  launch_command: string;
};

export type Game = { slug: string; name: string };
export type Device = { id: string; name: string };
export type LockInfo = { locked: boolean; device_id?: string; acquired_at?: string };
export type SaveMeta = { hash: string; pushed_at: string; device_id: string } | null;

let _base = "http://localhost:8765";
let _token = "";

export function configure(host: string, port: number, token: string): void {
  _base = `http://${host || "localhost"}:${port || 8765}`;
  _token = token;
}

async function _fetch<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${_base}${path}`, {
    method,
    headers: {
      ...(body ? { "Content-Type": "application/json" } : {}),
      Authorization: `Bearer ${_token}`,
    },
    body: body != null ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const msg = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(msg.detail ?? res.statusText);
  }
  return res.json();
}

export async function health(): Promise<boolean> {
  try {
    const res = await fetch(`${_base}/health`, { signal: AbortSignal.timeout(4000) });
    return res.ok;
  } catch {
    return false;
  }
}

export async function pair(masterToken: string, deviceId: string, deviceName: string): Promise<string> {
  const data = await fetch(`${_base}/pair`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ master_token: masterToken, device_id: deviceId, device_name: deviceName }),
  });
  if (!data.ok) throw new Error((await data.json()).detail);
  return (await data.json()).token;
}

export const listGames = (): Promise<Game[]> => _fetch("GET", "/games");
export const addGame = (name: string): Promise<Game> => _fetch("POST", "/games", { name });
export const updateGame = (slug: string, name: string): Promise<Game> =>
  _fetch("PUT", `/games/${slug}`, { name });
export const removeGame = (slug: string): Promise<void> => _fetch("DELETE", `/games/${slug}`);

export const getGameDevice = (slug: string): Promise<GameDeviceConfig> =>
  _fetch("GET", `/games/${slug}/device`);
export const setGameDevice = (slug: string, cfg: GameDeviceConfig): Promise<void> =>
  _fetch("PUT", `/games/${slug}/device`, cfg);

export const getLock = (slug: string): Promise<LockInfo> => _fetch("GET", `/games/${slug}/lock`);
export const getSaveMeta = async (slug: string): Promise<SaveMeta> => {
  const res = await fetch(`${_base}/games/${slug}/save/meta`, {
    headers: { Authorization: `Bearer ${_token}` },
  });
  if (res.status === 204) return null;
  return res.json();
};

export const listDevices = (): Promise<Device[]> => _fetch("GET", "/devices");
