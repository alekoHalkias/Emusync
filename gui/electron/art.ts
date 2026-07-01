// art:cache IPC — downloads a libretro thumbnail and caches it to disk.
// Returns a file:// URL for the cached image, or null if the fetch fails.
import { ipcMain } from "electron";
import { createWriteStream, existsSync, mkdirSync } from "fs";
import { join } from "path";
import { homedir } from "os";
import https from "https";

const ART_DIR        = join(homedir(), ".emusync", "art");
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
  saturn:  "Sega_-_Saturn",
  gg:      "Sega_-_Game_Gear",
  msx:     "Microsoft_-_MSX",
  atari2600: "Atari_-_2600",
  lynx:    "Atari_-_Lynx",
  ngpc:    "SNK_-_Neo_Geo_Pocket_Color",
  ws:      "Bandai_-_WonderSwan",
  wsc:     "Bandai_-_WonderSwan_Color",
};

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

function download(url: string, dest: string): Promise<void> {
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

export function registerArtIpc(): void {
  ipcMain.handle(
    "art:get",
    async (_event, slug: string, gameName: string, consoleKey: string): Promise<string | null> => {
      try {
        mkdirSync(ART_DIR, { recursive: true });
        const dest = join(ART_DIR, `${slug}.png`);
        if (existsSync(dest)) return `file://${dest}`;

        const url = buildThumbnailUrl(consoleKey, gameName);
        if (!url) return null;

        await download(url, dest);
        return existsSync(dest) ? `file://${dest}` : null;
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
        if (existsSync(dest)) return `file://${dest}`;

        const logoName = CONSOLE_LOGO[consoleKey.toLowerCase()];
        if (!logoName) return null;

        const url = `${RETROARCH_ASSETS_BASE}/${encodeURIComponent(logoName)}.png`;
        await download(url, dest);
        return existsSync(dest) ? `file://${dest}` : null;
      } catch {
        return null;
      }
    },
  );
}
