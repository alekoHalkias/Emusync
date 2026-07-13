// art:cache IPC — downloads a libretro thumbnail and caches it to disk.
// Returns a base64 data URL for the cached image, or null if the fetch fails.
// (file:// URLs are blocked by Chromium when the renderer is served from http://)
import { ipcMain } from "electron";
import { createWriteStream, existsSync, mkdirSync, readFileSync } from "fs";
import { join } from "path";
import { homedir } from "os";
import https from "https";
import { parse as parseTOML } from "smol-toml";
import SGDBImport from "steamgriddb";
import { getSteamGridDbKey } from "./steamgriddb";
import { CONFIG_PATH } from "./runtime";
import { loadServerCfg } from "./config-store";

// steamgriddb is a pure-ESM package ("type": "module"); the Electron main
// bundle is CJS and externalizes it as a plain require(), which resolves to
// the module namespace ({ default: SGDB }) rather than the class itself —
// unwrap .default defensively so `new SGDB(...)` gets the actual class either
// way the bundler happens to expose it.
const SGDB: typeof SGDBImport = (SGDBImport as any).default ?? SGDBImport;

export const ART_DIR = join(homedir(), ".emusync", "art");
const CONSOLE_DIR    = join(homedir(), ".emusync", "art", "consoles");

// EmuSync console key → libretro-thumbnails system folder name (used for boxart)
const LIBRETRO_SYSTEM: Record<string, string> = {
  gba:     "Nintendo_-_Game_Boy_Advance",
  gb:      "Nintendo_-_Game_Boy",
  gbc:     "Nintendo_-_Game_Boy_Color",
  snes:    "Nintendo_-_Super_Nintendo_Entertainment_System",
  nes:     "Nintendo_-_Nintendo_Entertainment_System",
  n64:     "Nintendo_-_Nintendo_64",
  nds:     "Nintendo_-_Nintendo_DS",
  "3ds":   "Nintendo_-_Nintendo_3DS",
  genesis: "Sega_-_Mega_Drive_-_Genesis",
  sms:     "Sega_-_Master_System_-_Mark_III",
  pce:     "NEC_-_PC_Engine_-_TurboGrafx_16",
  psx:     "Sony_-_PlayStation",
  ps2:     "Sony_-_PlayStation_2",
  psp:     "Sony_-_PlayStation_Portable",
  dc:      "Sega_-_Dreamcast",
  // Combined console (#402) — boxart fallback uses the GameCube repo; Wii
  // games rely on SteamGridDB (the primary source) for art.
  gamecube: "Nintendo_-_GameCube",
  saturn:  "Sega_-_Saturn",
  gg:      "Sega_-_Game_Gear",
  msx:     "Microsoft_-_MSX",
  atari2600: "Atari_-_2600",
  lynx:    "Atari_-_Lynx",
  ngpc:    "SNK_-_Neo_Geo_Pocket_Color",
  ws:      "Bandai_-_WonderSwan",
  wsc:     "Bandai_-_WonderSwan_Color",
};

export type ArtType = "grid" | "hero" | "logo" | "icon" | "wide_grid";
export const ART_TYPES: ArtType[] = ["grid", "hero", "logo", "icon", "wide_grid"];

// Per-console artwork type preference (issue #324) — read directly from the
// shared config file rather than passed through art:get's args, so the IPC
// signature stays unchanged and every caller automatically picks up a change.
function getArtType(consoleKey: string): ArtType {
  try {
    if (!existsSync(CONFIG_PATH)) return "grid";
    const cfg = parseTOML(readFileSync(CONFIG_PATH, "utf-8")) as Record<string, any>;
    const byConsole = (cfg.art_type_by_console ?? {}) as Record<string, string>;
    const type = byConsole[consoleKey];
    return (ART_TYPES as string[]).includes(type) ? (type as ArtType) : "grid";
  } catch {
    return "grid";
  }
}

function sanitizeGameName(name: string): string {
  // libretro thumbnail filenames replace certain chars with underscores
  return name
    .replace(/[/:]/g, "_")
    .replace(/[?*\\|"<>]/g, "_")
    .trim();
}

function buildThumbnailUrl(consoleKey: string, gameName: string): string | null {
  const system = LIBRETRO_SYSTEM[consoleKey.toLowerCase()];
  if (!system) return null;
  const encoded = encodeURIComponent(sanitizeGameName(gameName));
  return `https://raw.githubusercontent.com/libretro-thumbnails/${system}/master/Named_Boxarts/${encoded}.png`;
}

export function download(url: string, dest: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const tmp = dest + ".tmp";
    const file = createWriteStream(tmp);
    https.get(url, (res) => {
      if (res.statusCode !== 200) {
        file.destroy();
        reject(new Error(`HTTP ${res.statusCode}`));
        return;
      }
      res.pipe(file);
      file.on("finish", () => {
        file.close();
        // Rename atomically into place
        const fs = require("fs");
        try { fs.renameSync(tmp, dest); } catch { /* already there */ }
        resolve();
      });
    }).on("error", (err) => {
      file.destroy();
      reject(err);
    });
    file.on("error", (err) => {
      file.destroy();
      reject(err);
    });
  });
}

// Shared with gui/electron/artwork.ts (issue #325) so the ESM/CJS interop
// workaround above lives in exactly one place.
export function makeSteamGridDbClient(key: string): SGDBImport {
  return new SGDB({ key });
}

// Shared with gui/electron/artwork.ts (issue #325) — the one place that knows
// which SGDB method each artwork type maps to. Grid keeps its boxart-shaped
// portrait filter (600x900); Hero/Logo/Icon take SteamGridDB's results as-is
// — there's no single "right" size to filter to for those. Wide Grid (issue
// #333) has no single "right" dimension either — SteamGridDB serves landscape
// grid art at several sizes (460x215, 920x430, 700x200, ...) — so instead of
// an exact `dimensions` filter (which under-populated results, issue #341) it
// fetches every grid and keeps whichever are landscape-oriented by actual
// width/height.
// Hardcoded off, no setting exposed to turn them on (issue #326).
const SAFE_FILTER = { nsfw: "false", humor: "false" };

export async function getSgdbImagesForType(client: SGDBImport, sgdbGameId: number, artType: ArtType) {
  if (artType === "grid") {
    return client.getGrids({ id: sgdbGameId, type: "game", dimensions: ["600x900"], ...SAFE_FILTER });
  }
  if (artType === "wide_grid") {
    const images = await client.getGrids({ id: sgdbGameId, type: "game", ...SAFE_FILTER });
    return images.filter((img) => img.width > img.height);
  }
  if (artType === "hero") return client.getHeroes({ id: sgdbGameId, type: "game", ...SAFE_FILTER });
  if (artType === "logo") return client.getLogos({ id: sgdbGameId, type: "game", ...SAFE_FILTER });
  return client.getIcons({ id: sgdbGameId, type: "game", ...SAFE_FILTER });
}

// Shared with gui/electron/artwork.ts (issue #339) — resolves which SGDB game
// id to use: the already-picked/persisted `sgdb_game_id` if there is one,
// otherwise the top fuzzy-search result, which then gets persisted as the
// game's "first choice" so later fetches (on this device or any other) reuse
// it instead of re-searching and potentially landing on a different game. A
// manual pick in the Artwork tab overwrites `sgdb_game_id` directly and
// always wins — this only fills the gap while nothing has been chosen yet.
export async function resolveSgdbGameId(
  client: SGDBImport, slug: string, gameName: string,
): Promise<number | null> {
  try {
    const { host, port, authHeaders } = loadServerCfg();
    const res = await fetch(`http://${host}:${port}/games/${slug}`, {
      headers: authHeaders, signal: AbortSignal.timeout(5000),
    });
    if (res.ok) {
      const game = await res.json() as { name: string; sgdb_game_id: number | null };
      if (game.sgdb_game_id) return game.sgdb_game_id;
      const games = await client.searchGame(gameName);
      if (!games.length) return null;
      const found = games[0].id;
      try {
        await fetch(`http://${host}:${port}/games/${slug}`, {
          method: "PUT",
          headers: { ...authHeaders, "Content-Type": "application/json" },
          body: JSON.stringify({ name: game.name, sgdb_game_id: found }),
          signal: AbortSignal.timeout(5000),
        });
      } catch { /* best-effort — the fetched art is still correct this session */ }
      return found;
    }
  } catch { /* server unreachable — fall through to a one-off search below */ }
  const games = await client.searchGame(gameName);
  return games.length ? games[0].id : null;
}

async function fetchFromSteamGridDb(slug: string, gameName: string, dest: string, artType: ArtType): Promise<boolean> {
  const key = await getSteamGridDbKey();
  if (!key) return false;
  try {
    const client = makeSteamGridDbClient(key);
    const sgdbId = await resolveSgdbGameId(client, slug, gameName);
    if (!sgdbId) return false;
    const images = await getSgdbImagesForType(client, sgdbId, artType);
    if (!images.length) return false;
    await download(String(images[0].url), dest);
    return existsSync(dest);
  } catch {
    return false;
  }
}

// EmuSync console key → RetroArch XMB monochrome logo filename (spaces, not underscores)
const CONSOLE_LOGO: Record<string, string> = {
  gba:       "Nintendo - Game Boy Advance",
  gb:        "Nintendo - Game Boy",
  gbc:       "Nintendo - Game Boy Color",
  snes:      "Nintendo - Super Nintendo Entertainment System",
  nes:       "Nintendo - Nintendo Entertainment System",
  n64:       "Nintendo - Nintendo 64",
  nds:       "Nintendo - Nintendo DS",
  "3ds":     "Nintendo - Nintendo 3DS",
  genesis:   "Sega - Mega Drive - Genesis",
  sms:       "Sega - Master System - Mark III",
  pce:       "NEC - PC Engine - TurboGrafx 16",
  psx:       "Sony - PlayStation",
  ps2:       "Sony - PlayStation 2",
  psp:       "Sony - PlayStation Portable",
  dc:        "Sega - Dreamcast",
  gamecube:  "Nintendo - GameCube",
  saturn:    "Sega - Saturn",
  gg:        "Sega - Game Gear",
  msx:       "Microsoft - MSX",
  atari2600: "Atari - 2600",
  lynx:      "Atari - Lynx",
  ws:        "Bandai - WonderSwan",
  wsc:       "Bandai - WonderSwan Color",
};

const RETROARCH_ASSETS_BASE =
  "https://raw.githubusercontent.com/libretro/retroarch-assets/master/xmb/monochrome/png";

export function toDataUrl(filePath: string): string {
  const buf = readFileSync(filePath);
  return `data:image/png;base64,${buf.toString("base64")}`;
}

export function registerArtIpc(): void {
  ipcMain.handle(
    "art:get",
    async (_event, slug: string, gameName: string, consoleKey: string): Promise<string | null> => {
      try {
        // One folder per console, one subfolder per game (issue #304 follow-up),
        // one file per artwork type within it (issue #324) — e.g.
        // ~/.emusync/art/gba/pokemon-emerald/grid.png. Each type is cached
        // independently and permanently once fetched; switching a console's
        // configured type never deletes another type's cached file, it just
        // changes which one this device looks for/fetches next.
        const artType = getArtType(consoleKey);
        const gameDir = join(ART_DIR, consoleKey, slug);
        mkdirSync(gameDir, { recursive: true });
        const dest = join(gameDir, `${artType}.png`);
        if (existsSync(dest)) return toDataUrl(dest);

        // SteamGridDB's fuzzy title search finds far more games than the
        // exact-filename libretro-thumbnails lookup below; try it first when
        // a shared key is configured (issue #322).
        if (await fetchFromSteamGridDb(slug, gameName, dest, artType)) return toDataUrl(dest);

        // The libretro-thumbnails fallback is boxart-shaped only — there's no
        // equivalent for hero/logo/icon art, so those just show the
        // placeholder if SteamGridDB has no key/no match.
        if (artType !== "grid") return null;

        const url = buildThumbnailUrl(consoleKey, gameName);
        if (!url) return null;

        await download(url, dest);
        return existsSync(dest) ? toDataUrl(dest) : null;
      } catch {
        return null;
      }
    },
  );

  ipcMain.handle(
    "art:getConsoleIcon",
    async (_event, consoleKey: string): Promise<string | null> => {
      try {
        mkdirSync(CONSOLE_DIR, { recursive: true });
        const dest = join(CONSOLE_DIR, `${consoleKey}.png`);
        if (existsSync(dest)) return toDataUrl(dest);

        const logoName = CONSOLE_LOGO[consoleKey.toLowerCase()];
        if (!logoName) return null;

        const url = `${RETROARCH_ASSETS_BASE}/${encodeURIComponent(logoName)}.png`;
        await download(url, dest);
        return existsSync(dest) ? toDataUrl(dest) : null;
      } catch {
        return null;
      }
    },
  );
}
