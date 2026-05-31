/** Thin wrapper around the EmuSync Python REST API. */

export type GameDeviceConfig = {
  rom_path: string;
  save_path: string;
  launch_command: string;
  state_path?: string;
  rom_folder_path?: string;
};

export type Game = { slug: string; name: string; console?: string };
export type Device = { id: string; name: string; last_ip?: string | null; last_seen_at?: string | null };
export type LockInfo = { locked: boolean; device_id?: string; acquired_at?: string };
export type SaveMeta = { hash: string; pushed_at: string; device_id: string } | null;

let _base = "http://localhost:8765";
let _pin = "";
let _deviceId = "";
let _deviceName = "";

export function configure(host: string, port: number, pin: string): void {
  _base = `http://${host || "localhost"}:${port || 8765}`;
  _pin = pin;
}

export function configureDevice(deviceId: string, deviceName: string): void {
  _deviceId = deviceId;
  _deviceName = deviceName;
}

async function _fetch<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${_base}${path}`, {
    method,
    headers: {
      ...(body ? { "Content-Type": "application/json" } : {}),
      "Authorization": `Bearer ${_pin}`,
      "X-Device-ID": _deviceId,
      "X-Device-Name": _deviceName,
    },
    body: body != null ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(5000),
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

export const listGames = (): Promise<Game[]> => _fetch("GET", "/games");
export const addGame = (name: string, console?: string): Promise<Game> => _fetch("POST", "/games", { name, console });
export const updateGame = (slug: string, name: string): Promise<Game> =>
  _fetch("PUT", `/games/${slug}`, { name });
export const removeGame = (slug: string): Promise<void> => _fetch("DELETE", `/games/${slug}`);

export const getGameDevice = (slug: string): Promise<GameDeviceConfig> =>
  _fetch("GET", `/games/${slug}/device`);
export const setGameDevice = (slug: string, cfg: GameDeviceConfig): Promise<void> =>
  _fetch("PUT", `/games/${slug}/device`, cfg);

export const getLock = (slug: string): Promise<LockInfo> => _fetch("GET", `/games/${slug}/lock`);
export const releaseLock = (slug: string): Promise<void> => _fetch("DELETE", `/games/${slug}/lock`);
export const getSaveMeta = async (slug: string): Promise<SaveMeta> => {
  const res = await fetch(`${_base}/games/${slug}/save/meta`, {
    headers: {
      "Authorization": `Bearer ${_pin}`,
      "X-Device-ID": _deviceId,
      "X-Device-Name": _deviceName,
    },
    signal: AbortSignal.timeout(5000),
  });
  if (res.status === 204 || !res.ok) return null;
  return res.json();
};

export const getStateMeta = async (slug: string): Promise<SaveMeta> => {
  const res = await fetch(`${_base}/games/${slug}/state/meta`, {
    headers: {
      "Authorization": `Bearer ${_pin}`,
      "X-Device-ID": _deviceId,
      "X-Device-Name": _deviceName,
    },
    signal: AbortSignal.timeout(5000),
  });
  if (res.status === 204 || !res.ok) return null;
  return res.json();
};

export const listDevices = (): Promise<Device[]> => _fetch("GET", "/devices");
export const whoami = (): Promise<{ device_id: string }> => _fetch("GET", "/whoami");
export const removeDevice = (deviceId: string): Promise<void> => _fetch("DELETE", `/devices/${deviceId}`);

export type ActivityEvent = {
  type: string;
  game_slug: string | null;
  device_id: string | null;
  device_name: string | null;
  rom_path: string | null;
  occurred_at: string;
};

export const listEvents = (): Promise<ActivityEvent[]> => _fetch("GET", "/events");


export const listGameDevices = (slug: string): Promise<Device[]> => _fetch("GET", `/games/${slug}/devices`);

export type DeviceConsole = { console_name: string; device_game_folder: string; device_save_folder: string; device_emulator: string };
export type DeviceGameDevice = { slug: string; name: string; console?: string; rom_path: string; save_path: string };

export const getDeviceConsoles = (deviceId: string): Promise<DeviceConsole[]> =>
  _fetch("GET", `/devices/${deviceId}/consoles`);
export const getDeviceGameDevices = (deviceId: string): Promise<DeviceGameDevice[]> =>
  _fetch("GET", `/devices/${deviceId}/game-devices`);
export const createPullRequest = (slug: string, fromDeviceId: string, destinationPath: string): Promise<{ pull_request_id: string; status: string; source_online: boolean }> =>
  _fetch("POST", `/games/${slug}/rom-pull-request`, { from_device_id: fromDeviceId, destination_path: destinationPath });
