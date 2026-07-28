/** Thin wrapper around the EmuSync Python REST API. */

export type GameDeviceConfig = {
  rom_path: string;
  save_path: string;
  launch_command: string;
  state_path?: string;
  rom_folder_path?: string;
  // Network-ROM source fields (issue #255).
  rom_source?: string;        // 'local' | 'network'
  rom_rel_path?: string;
  local_rom_path?: string;
  rom_sha256?: string;
  // Transient hints (not stored on the game) used to populate the console row's
  // per-console network/local folders during a network import.
  device_network_folder?: string;
  device_local_folder?: string;
};

export type Game = { slug: string; name: string; console?: string; sgdb_game_id?: number | null };
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

export type GameOverview = {
  slug: string;
  name: string;
  console: string;
  locked: boolean;
  lock_device_id: string | null;
  last_push: string | null;
  is_local: boolean;
  rom_path: string;
  save_path: string;
  state_path: string;
  launch_command: string;
  rom_folder_path: string;
  rom_source: string;        // 'local' | 'network' (issue #255)
  rom_rel_path: string;
  local_rom_path: string;
};

/** One call returning lock + last save + this device's config for every game. */
export const gamesOverview = (): Promise<GameOverview[]> => _fetch("GET", "/games/overview");

export const listGames = (): Promise<Game[]> => _fetch("GET", "/games");
export const getGame = (slug: string): Promise<Game> => _fetch("GET", `/games/${slug}`);
export const addGame = (name: string, console?: string): Promise<Game> => _fetch("POST", "/games", { name, console });
export const updateGame = (slug: string, name: string): Promise<Game> =>
  _fetch("PUT", `/games/${slug}`, { name });
export const removeGame = (slug: string): Promise<void> => _fetch("DELETE", `/games/${slug}`);
// Unlinks the game from this device only — the game, its saves/states, and
// every other device's config are untouched (issue #343, tier 1 of delete).
export const removeGameDevice = (slug: string): Promise<void> => _fetch("DELETE", `/games/${slug}/device`);

// Persists a manually-picked SteamGridDB game match (issue #325), shared
// across every device via this same server-side row. The PUT route requires
// `name`, so fetch the game's current name first rather than widen the route
// to allow a partial update.
export const setGameSgdbId = async (slug: string, sgdbGameId: number): Promise<Game> => {
  const game = await getGame(slug);
  return _fetch("PUT", `/games/${slug}`, { name: game.name, sgdb_game_id: sgdbGameId });
};

export const getGameDevice = (slug: string): Promise<GameDeviceConfig> =>
  _fetch("GET", `/games/${slug}/device`);

// A network-drive config for this game on any device (issue #270) — lets a
// device without the game join the rel-path to its own mount root.
export type GameNetworkSource = {
  console: string;
  device_id: string;
  device_name: string;
  rom_path: string;
  rom_rel_path: string;
  launch_command: string;
  save_path: string;
  state_path: string;
  rom_folder_path: string;
};
export const getGameNetworkSource = (slug: string): Promise<GameNetworkSource> =>
  _fetch("GET", `/games/${slug}/network-source`);
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

export const getConsoleMemcardMeta = async (consoleKey: string): Promise<SaveMeta> => {
  const res = await fetch(`${_base}/consoles/${consoleKey}/memcard/meta`, {
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


// Devices that have this game configured, with their ROM/save paths (the
// `/games/{slug}/devices` payload carries more than a bare Device).
export type DeviceForGame = Device & {
  rom_path?: string; save_path?: string; state_path?: string; rom_folder_path?: string;
};
export const listGameDevices = (slug: string): Promise<DeviceForGame[]> => _fetch("GET", `/games/${slug}/devices`);

export type SaveVersion = { id: string; device_id: string; hash: string; pushed_at: string; size: number };

/** Retained save generations for a game, newest first (issue #7). */
export const listSaveHistory = (slug: string): Promise<SaveVersion[]> =>
  _fetch("GET", `/games/${slug}/save/history`);
/** Make a past save version current on the server. */
export const restoreSave = (slug: string, versionId: string): Promise<{ hash: string; pushed_at: string }> =>
  _fetch("POST", `/games/${slug}/save/restore`, { version_id: versionId });

/** Retained state generations for a game, newest first (issue #7/#285). */
export const listStateHistory = (slug: string): Promise<SaveVersion[]> =>
  _fetch("GET", `/games/${slug}/state/history`);
/** Make a past state version current on the server. */
export const restoreState = (slug: string, versionId: string): Promise<{ hash: string; pushed_at: string }> =>
  _fetch("POST", `/games/${slug}/state/restore`, { version_id: versionId });

// ── integrity / recovery (issue #285) ───────────────────────────────────────────

export type IntegrityReason = "zero_byte" | "shrank" | "hash_mismatch" | "file_missing";
export type BlobIntegrity = {
  status: "ok" | "damaged" | "missing";
  reasons: IntegrityReason[];
  size: number | null;
  hash: string | null;
  pushed_at: string | null;
  prior_size: number | null;
  last_good_version_id: string | null;
};
export type GameIntegrity = { save: BlobIntegrity; state: BlobIntegrity };

/** Integrity verdicts for a game's current save + state blobs (recomputed). */
export const getGameIntegrity = (slug: string): Promise<GameIntegrity> =>
  _fetch("GET", `/games/${slug}/integrity`);
/** Re-run the library-wide integrity sweep and return the damaged blobs. */
export const rescanIntegrity = (): Promise<{ scanned: number; damaged: Array<{ slug: string; name: string; kind: string; reasons: IntegrityReason[]; last_good_version_id: string | null }> }> =>
  _fetch("POST", "/integrity/rescan");

export type DeviceConsole = { console_name: string; device_game_folder: string; device_save_folder: string; device_emulator: string; device_network_folder?: string; device_local_folder?: string };
export type DeviceGameDevice = { slug: string; name: string; console?: string; rom_path: string; save_path: string };

export const getDeviceConsoles = (deviceId: string): Promise<DeviceConsole[]> =>
  _fetch("GET", `/devices/${deviceId}/consoles`);
export const getDeviceGameDevices = (deviceId: string): Promise<DeviceGameDevice[]> =>
  _fetch("GET", `/devices/${deviceId}/game-devices`);
export const createPullRequest = (slug: string, fromDeviceId: string, destinationPath: string): Promise<{ pull_request_id: string; status: string; source_online: boolean }> =>
  _fetch("POST", `/games/${slug}/rom-pull-request`, { from_device_id: fromDeviceId, destination_path: destinationPath });

// ── save conflicts (issue #243) ────────────────────────────────────────────────

export type SaveConflict = {
  id: string;
  game_slug: string;
  game_name: string;
  winner_device_id: string;
  loser_device_id: string;
  winner_hash: string;
  loser_hash: string;
  resolved_at: string;
  winner_device_name: string | null;
  loser_device_name: string | null;
};

/** Open (un-dismissed) save conflicts across all games, newest first. */
export const listConflicts = (): Promise<SaveConflict[]> => _fetch("GET", "/conflicts");
/** Dismiss a conflict so it no longer shows in the panel. */
export const dismissConflict = (id: string): Promise<{ ok: boolean }> =>
  _fetch("POST", `/conflicts/${id}/dismiss`);
