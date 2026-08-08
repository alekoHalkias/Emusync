// Switch title-ID lookup by name (issue #448) — matches a game's display name
// against blawar/titledb's public US.en.json catalog (an unauthenticated,
// static name<->title-ID list; no Switch keys/NCA decryption involved, unlike
// reading the ID out of the ROM itself). Mirrors the SteamGridDB name-match
// pattern (art.ts's resolveSgdbGameId), but with a strict exact match only —
// a wrong guess would seed a save into the wrong title's Eden save folder
// (same reasoning as the Wii NAND-folder gotcha in CLAUDE.md), so a miss just
// falls through to the existing bracket-tag/post-launch self-heal path
// (#419/#443) instead of risking a bad one.
import { ipcMain } from "electron";
import { existsSync, readFileSync, writeFileSync, statSync } from "fs";
import { join } from "path";
import { homedir } from "os";
import { spawn } from "child_process";
import { SCRIPT, PYTHON } from "./runtime";

const TITLEDB_URL = "https://raw.githubusercontent.com/blawar/titledb/master/US.en.json";
// ponytail: the raw catalog is ~85MB (it bundles descriptions/box-art URLs we
// don't need) — no lighter published dataset exists for this project, so the
// full file is fetched once and immediately distilled down to just this tiny
// slug->titleId map before being written to disk. Only the very first lookup
// ever pays the big download; every later one (any device, any run) reads the
// small cached file below until it's 30 days old.
const CACHE_PATH = join(homedir(), ".emusync", "switch_titledb.json");
const CACHE_MAX_AGE_MS = 30 * 24 * 60 * 60 * 1000; // 30 days

// Local since electron/ doesn't share code with gui/renderer/src's helpers.ts.
// NFD-normalize + strip combining marks first so accented letters (titledb's
// "Pokémon™ Sword" vs. a plain-ASCII ROM dump's "Pokemon Sword") fold to their
// base letter instead of being dropped outright — [^a-z0-9] alone silently
// deleted the accented character rather than transliterating it, which broke
// matching for most of the catalog.
function slugify(name: string): string {
  return name
    .normalize("NFD").replace(/[\u0300-\u036f]/g, "") // strip combining diacritics
    .toLowerCase().replace(/[^a-z0-9]+/g, "");
}

let cachedMap: Map<string, string> | null = null; // slugified name -> title id, this process's lifetime

async function buildDistilledMap(): Promise<Map<string, string>> {
  const res = await fetch(TITLEDB_URL, { signal: AbortSignal.timeout(60000) });
  if (!res.ok) throw new Error(`titledb fetch failed: ${res.status}`);
  const raw = await res.json() as Record<string, { id?: string; name?: string }>;
  const map = new Map<string, string>();
  for (const entry of Object.values(raw)) {
    if (!entry?.id || !entry.name) continue;
    // Base titles only — low 3 hex digits "000" (mirrors cli/detect.py's
    // _SWITCH_TITLE_ID_RE convention for filtering update/DLC packages).
    if (!entry.id.toLowerCase().endsWith("000")) continue;
    const slug = slugify(entry.name);
    if (slug && !map.has(slug)) map.set(slug, entry.id.toUpperCase());
  }
  return map;
}

async function getTitleMap(): Promise<Map<string, string>> {
  if (cachedMap) return cachedMap;
  if (existsSync(CACHE_PATH) && Date.now() - statSync(CACHE_PATH).mtimeMs < CACHE_MAX_AGE_MS) {
    try {
      cachedMap = new Map(Object.entries(JSON.parse(readFileSync(CACHE_PATH, "utf-8"))));
      return cachedMap;
    } catch { /* corrupt/unreadable cache — refetch below */ }
  }
  const map = await buildDistilledMap();
  try { writeFileSync(CACHE_PATH, JSON.stringify(Object.fromEntries(map))); } catch { /* best effort — refetches next time */ }
  cachedMap = map;
  return map;
}

export async function lookupSwitchTitleId(gameName: string): Promise<string | null> {
  try {
    const map = await getTitleMap();
    return map.get(slugify(gameName)) ?? null;
  } catch {
    return null; // network/parse failure — caller falls back to existing paths
  }
}

// Makes sure this device has a save folder for a game once its title ID is
// known (issue #448, extended by #453): seeds a real save from the server if
// another device already has one, otherwise creates an empty
// <profile>/<title-id>/ placeholder in every local Eden profile that doesn't
// have one yet. Shells out to the CLI (mirrors switchmods.ts's "sync now"
// spawn) since cli/run_switch.py already owns the profile-enumeration and
// seeding logic — see cli/game.py's ensure-switch-save-folder command.
export function ensureSwitchSaveFolder(slug: string): Promise<{ ok: boolean; output: string }> {
  return new Promise((resolve) => {
    const proc = spawn(PYTHON, [SCRIPT, "game", "ensure-switch-save-folder", slug]);
    let output = "";
    proc.stdout.on("data", (d) => (output += d.toString()));
    proc.stderr.on("data", (d) => (output += d.toString()));
    proc.on("close", (code) => resolve({ ok: code === 0, output: output.trim() }));
    proc.on("error", (e: Error) => resolve({ ok: false, output: e.message }));
  });
}

export function registerSwitchTitleDbIpc(): void {
  ipcMain.handle("switchTitleDb:lookup", (_event, gameName: string): Promise<string | null> =>
    lookupSwitchTitleId(gameName)
  );
  ipcMain.handle("switchTitleDb:ensureSaveFolder", (_event, slug: string): Promise<{ ok: boolean; output: string }> =>
    ensureSwitchSaveFolder(slug)
  );
}
