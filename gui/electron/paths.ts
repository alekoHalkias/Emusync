// Where EmuSync keeps its files (#564). Mirrors server/paths.py — keep the two
// in step (tests/test_paths.py compares them). config: emusync.toml/display.json;
// data: db, blobs, game_cache, pid/token, per-game art; cache: regenerable downloads.
// EMUSYNC_{CONFIG,DATA,CACHE}_DIR override any platform.
import { existsSync, readFileSync } from "fs";
import { join, isAbsolute } from "path";
import { homedir } from "os";
import { parse as parseTOML } from "smol-toml";

type Kind = "config" | "data" | "cache";

function base(kind: Kind): string {
  const override = process.env[`EMUSYNC_${kind.toUpperCase()}_DIR`];
  if (override) return override;
  const home = homedir();
  if (process.platform === "win32") {
    const roaming = process.env.APPDATA || join(home, "AppData", "Roaming");
    const local = process.env.LOCALAPPDATA || join(home, "AppData", "Local");
    return kind === "cache" ? join(local, "emusync", "cache") : join(roaming, "emusync");
  }
  if (process.platform === "darwin") {
    const lib = join(home, "Library");
    return kind === "cache" ? join(lib, "Caches", "emusync") : join(lib, "Application Support", "emusync");
  }
  const [envVar, fallback] = { config: ["XDG_CONFIG_HOME", ".config"], data: ["XDG_DATA_HOME", ".local/share"], cache: ["XDG_CACHE_HOME", ".cache"] }[kind];
  const root = process.env[envVar];
  return join(root && isAbsolute(root) ? root : join(home, fallback), "emusync");
}

export const configDir = (): string => base("config");
export const cacheDir = (): string => base("cache");
export const CONFIG_PATH = join(configDir(), "emusync.toml");

// The server's data dir is `data_dir` in emusync.toml when set (Python honours it
// everywhere), else the platform default — so Electron and the CLI always agree.
export function dataDir(): string {
  try {
    if (existsSync(CONFIG_PATH)) {
      const d = (parseTOML(readFileSync(CONFIG_PATH, "utf-8")) as Record<string, unknown>).data_dir;
      if (typeof d === "string" && d) return d;
    }
  } catch { /* unreadable config: fall through to the default */ }
  return base("data");
}
