// Steam import (issue #385): add a per-game non-Steam-game shortcut to the
// local Steam client, copy EmuSync's already-cached artwork into Steam's grid
// folder, and best-effort group the game into a console-named Collection.
//
// Steam's shortcuts.vdf is a small, well-known binary format handled by the
// `steam-shortcut-editor` npm package rather than a hand-rolled parser — this
// file is the ONLY record of every non-Steam game shortcut the user has, not
// just EmuSync's, so a subtly wrong hand-rolled writer risks corrupting or
// dropping unrelated entries.
//
// Steam's "Collections" (grouping) storage is undocumented and has changed
// format across client versions; this best-effort implementation follows the
// scheme used by community tools (SteamGridDB Manager, steam-rom-manager) as
// of 2024 — a JSON blob under the "user-collections" key inside
// config/localconfig.vdf's plaintext (non-binary) VDF. If that key isn't
// found, the shortcut + artwork are still applied and a warning is returned
// instead of failing outright (ponytail: no live Steam install available to
// verify byte-for-byte against; verify manually and adjust if this proves
// wrong on a real client).
import { ipcMain } from "electron";
import { spawn } from "child_process";
import { existsSync, readdirSync, readFileSync, statSync, writeFileSync, mkdirSync, copyFileSync } from "fs";
import { join, dirname } from "path";
import { homedir, platform } from "os";
import shortcutEditor from "steam-shortcut-editor";
import { SCRIPT } from "./runtime";
import { ART_DIR } from "./art";

type SteamShortcut = {
  appid?: number;
  AppName?: string;
  exe?: string;
  StartDir?: string;
  icon?: string;
  ShortcutPath?: string;
  LaunchOptions?: string;
  IsHidden?: boolean;
  AllowDesktopConfig?: boolean;
  AllowOverlay?: boolean;
  OpenVR?: boolean;
  Devkit?: boolean;
  DevkitGameID?: string;
  DevkitOverrideAppID?: boolean;
  LastPlayTime?: number;
  tags?: string[];
};

// Standard CRC-32 (IEEE 802.3), matching Python's binascii.crc32 / zlib.crc32
// for the same UTF-8 bytes — no crc32 in Node's stdlib, so a small table-based
// implementation instead of pulling in a dependency for one function.
const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c >>> 0;
  }
  return table;
})();

function crc32(str: string): number {
  const bytes = Buffer.from(str, "utf8");
  let crc = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) {
    crc = CRC_TABLE[(crc ^ bytes[i]) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

/** Steam's non-Steam-game appid: unsigned crc32(rawExe+name) with the top bit
 * forced on. Two hard-won constraints, both confirmed on a real client:
 * - Hash the RAW, unquoted exe path — quotes are only added when serializing
 *   the `exe` field into shortcuts.vdf, they are not part of the hash input.
 * - This UNSIGNED 32-bit value is what keys the modern library's artwork
 *   filenames (<appid>p.png etc.) and collection entries. The 64-bit
 *   (crc<<32)|0x02000000 variant floating around community docs is only the
 *   legacy Big Picture banner id — name the files with it and Steam silently
 *   ignores them. */
function shortcutAppId(rawExe: string, name: string): number {
  return (crc32(rawExe + name) | 0x80000000) >>> 0;
}

function findSteamDir(): string | null {
  const candidates = platform() === "win32"
    ? [
        process.env["ProgramFiles(x86)"] ? join(process.env["ProgramFiles(x86)"], "Steam") : null,
        process.env.ProgramFiles ? join(process.env.ProgramFiles, "Steam") : null,
      ]
    : [
        join(homedir(), ".steam", "steam"),
        join(homedir(), ".local", "share", "Steam"),
        join(homedir(), ".var", "app", "com.valvesoftware.Steam", ".local", "share", "Steam"),
      ];
  for (const c of candidates) {
    if (c && existsSync(join(c, "userdata"))) return c;
  }
  return null;
}

/** Picks the active Steam account's userdata folder. With more than one
 * account on the machine, falls back to whichever has the most recently
 * modified localconfig.vdf (ponytail: cheap heuristic — proper detection
 * needs parsing loginusers.vdf's "mostrecent" flag; upgrade if this guesses
 * wrong for multi-account setups in practice). */
function findActiveUserdataDir(steamDir: string): string | null {
  const userdataRoot = join(steamDir, "userdata");
  const accounts = readdirSync(userdataRoot, { withFileTypes: true })
    .filter((d) => d.isDirectory() && /^\d+$/.test(d.name))
    .map((d) => join(userdataRoot, d.name));
  if (accounts.length === 0) return null;
  if (accounts.length === 1) return accounts[0];
  let best = accounts[0];
  let bestMtime = 0;
  for (const dir of accounts) {
    const cfg = join(dir, "config", "localconfig.vdf");
    if (!existsSync(cfg)) continue;
    const mtime = statSync(cfg).mtimeMs;
    if (mtime > bestMtime) { bestMtime = mtime; best = dir; }
  }
  return best;
}

/** Case-insensitive property lookup. Steam rewrites shortcuts.vdf with its
 * own key casing on restart (exe→Exe, AppName→appname, varies by client
 * version), so matching our previously written entry by exact-cased property
 * names silently fails after a Steam restart and duplicates the shortcut. */
function propCI(s: Record<string, unknown>, name: string): unknown {
  const lower = name.toLowerCase();
  const key = Object.keys(s).find((k) => k.toLowerCase() === lower);
  return key === undefined ? undefined : s[key];
}

const stripQuotes = (v: unknown): string => (typeof v === "string" ? v.replace(/^"+|"+$/g, "") : "");

/** If the entry is an EmuSync shortcut (our launcher exe, `run <slug>`
 * LaunchOptions), return its slug; else null. The single matcher behind
 * steam:addGame's upsert/dedup, steam:isAdded, and steam:addedSlugs so they
 * can never disagree about what counts as ours. */
function ourSlug(s: SteamShortcut, launcherExe: string): string | null {
  if (stripQuotes(propCI(s, "exe")) !== launcherExe) return null;
  const m = stripQuotes(propCI(s, "LaunchOptions")).match(/^run (.+)$/);
  return m ? m[1] : null;
}

function isOurShortcut(s: SteamShortcut, launcherExe: string, launchOptions: string): boolean {
  return `run ${ourSlug(s, launcherExe)}` === launchOptions;
}

function parseShortcutsFile(path: string): Promise<{ shortcuts: SteamShortcut[] }> {
  return new Promise((resolve, reject) => {
    if (!existsSync(path)) { resolve({ shortcuts: [] }); return; }
    shortcutEditor.parseFile(path, (err: Error | null, obj: any) => {
      if (err) { reject(err); return; }
      const shortcuts = Array.isArray(obj?.shortcuts) ? obj.shortcuts : [];
      resolve({ shortcuts });
    });
  });
}

function writeShortcutsFile(path: string, obj: { shortcuts: SteamShortcut[] }): Promise<void> {
  return new Promise((resolve, reject) => {
    shortcutEditor.writeFile(path, obj, (err: Error | null) => (err ? reject(err) : resolve()));
  });
}

type CloudEntry = {
  key: string;
  timestamp: number;
  value?: string;
  version?: string;
  is_deleted?: boolean;
  conflictResolutionMethod?: string;
  strMethodId?: string;
};

/** Upserts this console's collection in the modern client's collections store:
 * `config/cloudstorage/cloud-storage-namespace-1.json`, an array of
 * [key, entry] pairs where a live collection entry's `value` is a JSON string
 * `{id, name, added: [unsigned appids], removed: []}` (format confirmed
 * against a real 2026 client — issue #387; the localconfig.vdf
 * "user-collections" key that #385 originally targeted is legacy and ignored
 * by these clients). Deleted collections persist as `is_deleted` tombstones
 * and must not be resurrected. Every write bumps both the entry version and
 * namespace 1's version in cloud-storage-namespaces.json — Steam reconciles
 * local vs cloud state by comparing these.
 *
 * Reuses an existing live collection with the same *name* (e.g. one made by
 * Steam ROM Manager) rather than creating a parallel duplicate; otherwise
 * creates `emusync-<base64(name)>`, mirroring SRM's `srm-<base64(name)>`
 * convention. Returns false if the store isn't present/parseable — the
 * caller then falls back to the legacy localconfig.vdf path. */
function upsertCloudCollection(userdataDir: string, consoleName: string, appid: number): boolean {
  const csDir = join(userdataDir, "config", "cloudstorage");
  const nsPath = join(csDir, "cloud-storage-namespace-1.json");
  const namespacesPath = join(csDir, "cloud-storage-namespaces.json");
  if (!existsSync(nsPath) || !existsSync(namespacesPath)) return false;

  let pairs: [string, CloudEntry][];
  let namespaces: [number, string][];
  try {
    pairs = JSON.parse(readFileSync(nsPath, "utf8"));
    namespaces = JSON.parse(readFileSync(namespacesPath, "utf8"));
    if (!Array.isArray(pairs) || !Array.isArray(namespaces)) return false;
  } catch {
    return false; // format surprise — bail out rather than guess
  }
  const ns1 = namespaces.find((n) => n[0] === 1);
  if (!ns1) return false;
  const newVersion = String((parseInt(ns1[1], 10) || 0) + 1);
  const now = Math.floor(Date.now() / 1000);

  // Prefer a live collection already named after this console, whoever made it.
  let target: CloudEntry | undefined;
  for (const [key, entry] of pairs) {
    if (!key.startsWith("user-collections.") || entry.is_deleted || !entry.value) continue;
    try {
      if (JSON.parse(entry.value).name === consoleName) { target = entry; break; }
    } catch { /* skip unparseable entry */ }
  }

  if (target) {
    const val = JSON.parse(target.value!);
    val.added = val.added ?? [];
    if (!val.added.includes(appid)) val.added.push(appid);
    val.removed = (val.removed ?? []).filter((a: number) => a !== appid);
    target.value = JSON.stringify(val);
    target.timestamp = now;
    target.version = newVersion;
  } else {
    const id = `emusync-${Buffer.from(consoleName, "utf8").toString("base64")}`;
    const key = `user-collections.${id}`;
    const entry: CloudEntry = {
      key,
      timestamp: now,
      value: JSON.stringify({ id, name: consoleName, added: [appid], removed: [] }),
      version: newVersion,
      conflictResolutionMethod: "custom",
      strMethodId: "union-collections",
    };
    // Replace our own tombstone if the collection was deleted before, else append.
    const idx = pairs.findIndex(([k]) => k === key);
    if (idx >= 0) pairs[idx] = [key, entry];
    else pairs.push([key, entry]);
  }

  writeFileSync(nsPath, JSON.stringify(pairs), "utf8");
  ns1[1] = newVersion;
  writeFileSync(namespacesPath, JSON.stringify(namespaces), "utf8");
  return true;
}

/** Legacy fallback for clients without a cloudstorage store: upserts the
 * "user-collections" string value inside localconfig.vdf's plaintext VDF,
 * leaving everything else in the file byte-for-byte untouched. Returns false
 * (no-op) if that key isn't found — a documented fallback, not an error. */
function upsertCollection(localconfigPath: string, consoleName: string, appid: number): boolean {
  if (!existsSync(localconfigPath)) return false;
  const text = readFileSync(localconfigPath, "utf8");
  const re = /"user-collections"\s*"((?:[^"\\]|\\.)*)"/;
  const match = text.match(re);
  if (!match) return false;

  const unescape = (s: string) => s.replace(/\\"/g, '"').replace(/\\\\/g, "\\");
  const escape = (s: string) => s.replace(/\\/g, "\\\\").replace(/"/g, '\\"');

  let collections: Record<string, { id: string; name: string; added: number[]; removed: number[] }>;
  try {
    collections = JSON.parse(unescape(match[1]));
  } catch {
    return false; // format surprise — bail out rather than guess
  }

  const key = `emusync-${consoleName}`;
  const existing = collections[key];
  if (existing) {
    if (!existing.added.includes(appid)) existing.added.push(appid);
  } else {
    collections[key] = { id: key, name: consoleName, added: [appid], removed: [] };
  }

  const newValue = escape(JSON.stringify(collections));
  const newText = text.slice(0, match.index!) + `"user-collections"\t\t"${newValue}"` + text.slice(match.index! + match[0].length);
  writeFileSync(localconfigPath, newText, "utf8");
  return true;
}

/** Linux Steam's pid-file liveness check. Windows has no equally reliable
 * equivalent, so this reports false there and the restart-dialog flow (#393)
 * degrades to the write-time guard inside steam:addGame. */
function steamIsRunning(): boolean {
  if (platform() === "win32") return false;
  const pidFile = join(homedir(), ".steam", "steam.pid");
  if (!existsSync(pidFile)) return false;
  try {
    const pid = parseInt(readFileSync(pidFile, "utf8").trim(), 10);
    if (!pid) return false;
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function registerSteamIpc(): void {
  ipcMain.handle("steam:isRunning", () => steamIsRunning());

  // Graceful shutdown for the restart-to-add flow (#393): `steam -shutdown`
  // (NOT a pid kill — Steam rewrites shortcuts.vdf/collections on its own
  // exit, exactly the files about to be edited), then poll until the process
  // is really gone plus a short grace period for file flushing.
  ipcMain.handle("steam:shutdown", async (): Promise<{ ok: boolean; error?: string }> => {
    if (!steamIsRunning()) return { ok: true };
    try {
      spawn("steam", ["-shutdown"], { stdio: "ignore", detached: true }).unref();
    } catch (e: any) {
      return { ok: false, error: `Couldn't ask Steam to shut down: ${e.message || e}` };
    }
    for (let waited = 0; waited < 30_000; waited += 500) {
      await sleep(500);
      if (!steamIsRunning()) {
        await sleep(2000); // grace for Steam's own file writes to land
        return { ok: true };
      }
    }
    return { ok: false, error: "Steam didn't shut down within 30 seconds." };
  });

  // Detached relaunch after the writes; failure is a warning, not an error —
  // the shortcuts were already added successfully.
  ipcMain.handle("steam:launch", (): { ok: boolean; error?: string } => {
    try {
      spawn("steam", { stdio: "ignore", detached: true }).unref();
      return { ok: true };
    } catch (e: any) {
      return { ok: false, error: e.message || "Couldn't relaunch Steam." };
    }
  });

  // Read-only: whether this game already has an EmuSync shortcut in Steam.
  // Safe with Steam running; any failure (no Steam, unreadable shortcuts.vdf)
  // reports false so the Add button stays enabled and the add path surfaces
  // its own errors (issue #389).
  ipcMain.handle("steam:isAdded", async (_event, slug: string): Promise<boolean> => {
    try {
      const steamDir = findSteamDir();
      if (!steamDir) return false;
      const userdataDir = findActiveUserdataDir(steamDir);
      if (!userdataDir) return false;
      const parsed = await parseShortcutsFile(join(userdataDir, "config", "shortcuts.vdf"));
      const launcherExe = join(dirname(SCRIPT), "emusync");
      return parsed.shortcuts.some((s) => isOurShortcut(s, launcherExe, `run ${slug}`));
    } catch {
      return false;
    }
  });

  // Batch form of steam:isAdded for the game grid (issue #391): one parse of
  // shortcuts.vdf instead of one per game. Failures report [] so the grid
  // behaves as if nothing were added.
  ipcMain.handle("steam:addedSlugs", async (): Promise<string[]> => {
    try {
      const steamDir = findSteamDir();
      if (!steamDir) return [];
      const userdataDir = findActiveUserdataDir(steamDir);
      if (!userdataDir) return [];
      const parsed = await parseShortcutsFile(join(userdataDir, "config", "shortcuts.vdf"));
      const launcherExe = join(dirname(SCRIPT), "emusync");
      return parsed.shortcuts
        .map((s) => ourSlug(s, launcherExe))
        .filter((slug): slug is string => slug !== null);
    } catch {
      return [];
    }
  });

  ipcMain.handle(
    "steam:addGame",
    async (_event, slug: string, gameName: string, consoleName: string, consoleKey: string):
      Promise<{ ok: boolean; updated?: boolean; warning?: string; error?: string }> => {
      const steamDir = findSteamDir();
      if (!steamDir) return { ok: false, error: "Steam installation not found on this device." };

      const userdataDir = findActiveUserdataDir(steamDir);
      if (!userdataDir) return { ok: false, error: "No Steam account found — log into Steam at least once first." };

      // Refuse while Steam owns the file — it overwrites shortcuts.vdf on its
      // own shutdown/startup, silently clobbering whatever we just wrote.
      // Safety net behind the renderer's restart-dialog flow (#393).
      if (steamIsRunning()) {
        return { ok: false, error: "Steam appears to be running. Close Steam first, then try again." };
      }

      const launcherExe = join(dirname(SCRIPT), "emusync");
      const exe = `"${launcherExe}"`;
      const startDir = `"${dirname(launcherExe)}"`;
      const launchOptions = `run ${slug}`;

      const configDir = join(userdataDir, "config");
      mkdirSync(configDir, { recursive: true });
      const shortcutsPath = join(configDir, "shortcuts.vdf");

      let parsed: { shortcuts: SteamShortcut[] };
      try {
        parsed = await parseShortcutsFile(shortcutsPath);
      } catch (e: any) {
        return { ok: false, error: `Failed to read shortcuts.vdf: ${e.message || e}` };
      }

      const appid = shortcutAppId(launcherExe, gameName);
      // shortcuts.vdf stores the same 32 bits as a signed int32.
      const signedAppid = appid > 0x7fffffff ? appid - 0x100000000 : appid;
      const artSrcDir = join(ART_DIR, consoleKey, slug);
      const cachedIcon = join(artSrcDir, "icon.png");
      // Filtering (not findIndex) also collapses duplicates left by earlier runs.
      const others = parsed.shortcuts.filter((s) => !isOurShortcut(s, launcherExe, launchOptions));
      const alreadyAdded = others.length < parsed.shortcuts.length;
      const entry: SteamShortcut = {
        appid: signedAppid,
        AppName: gameName,
        exe,
        StartDir: startDir,
        icon: existsSync(cachedIcon) ? cachedIcon : "",
        ShortcutPath: "",
        LaunchOptions: launchOptions,
        IsHidden: false,
        AllowDesktopConfig: true,
        AllowOverlay: true,
        OpenVR: false,
        Devkit: false,
        DevkitGameID: "",
        DevkitOverrideAppID: false,
        LastPlayTime: 0,
        tags: [],
      };
      others.push(entry);

      try {
        await writeShortcutsFile(shortcutsPath, { shortcuts: others });
      } catch (e: any) {
        return { ok: false, error: `Failed to write shortcuts.vdf: ${e.message || e}` };
      }

      // Artwork: copy whatever EmuSync already cached — never block on a
      // missing type. Steam's grid folder naming, keyed by the UNSIGNED appid:
      // <id>p = portrait grid, <id> (bare) = wide/header capsule,
      // <id>_hero = hero banner, <id>_logo = logo overlay.
      const gridDir = join(configDir, "grid");
      mkdirSync(gridDir, { recursive: true });
      const artMap: [string, string][] = [
        ["grid", `${appid}p.png`],
        ["wide_grid", `${appid}.png`],
        ["hero", `${appid}_hero.png`],
        ["logo", `${appid}_logo.png`],
      ];
      for (const [type, destName] of artMap) {
        const src = join(artSrcDir, `${type}.png`);
        if (existsSync(src)) {
          try { copyFileSync(src, join(gridDir, destName)); } catch { /* non-fatal, skip this asset */ }
        }
      }

      let warning: string | undefined;
      const localconfigPath = join(configDir, "localconfig.vdf");
      try {
        // Modern clients store collections in cloudstorage; the localconfig.vdf
        // key still exists on them but is ignored, so it's only the fallback.
        const grouped = upsertCloudCollection(userdataDir, consoleName, appid)
          || upsertCollection(localconfigPath, consoleName, appid);
        if (!grouped) {
          warning = "Shortcut and artwork added, but this Steam client's Collections storage wasn't recognized — add it to a collection manually.";
        }
      } catch {
        warning = "Shortcut and artwork added, but updating Steam Collections failed — add it to a collection manually.";
      }

      return { ok: true, updated: alreadyAdded, warning };
    }
  );
}
