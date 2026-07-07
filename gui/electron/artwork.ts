// artwork:* IPC — per-game SteamGridDB search, candidate browsing, and manual
// per-type art selection (issue #325). Complements art.ts's automatic art:get:
// this lets a user override what auto-fetch picked, per game and per type.
import { ipcMain } from "electron";
import { existsSync, mkdirSync, unlinkSync } from "fs";
import { join } from "path";
import {
  ART_DIR, ART_TYPES, ArtType,
  download, getSgdbImagesForType, makeSteamGridDbClient, toDataUrl,
} from "./art";
import { getSteamGridDbKey } from "./steamgriddb";

export type SgdbGameResult = { id: number; name: string; release_date: number; verified: boolean };
export type SgdbCandidate = { id: number; thumb: string; url: string };

function gameDir(consoleKey: string, slug: string): string {
  return join(ART_DIR, consoleKey, slug);
}

export function registerArtworkIpc(): void {
  ipcMain.handle("artwork:searchGames", async (_event, name: string): Promise<SgdbGameResult[]> => {
    const key = await getSteamGridDbKey();
    if (!key) return [];
    try {
      const games = await makeSteamGridDbClient(key).searchGame(name);
      return games.map((g) => ({ id: g.id, name: g.name, release_date: g.release_date, verified: g.verified }));
    } catch {
      return [];
    }
  });

  ipcMain.handle(
    "artwork:listCandidates",
    async (_event, sgdbGameId: number, type: ArtType): Promise<SgdbCandidate[]> => {
      const key = await getSteamGridDbKey();
      if (!key) return [];
      try {
        const client = makeSteamGridDbClient(key);
        const images = await getSgdbImagesForType(client, sgdbGameId, type);
        return images.map((img) => ({ id: img.id, thumb: String(img.thumb), url: String(img.url) }));
      } catch {
        return [];
      }
    },
  );

  ipcMain.handle(
    "artwork:setArt",
    async (_event, slug: string, consoleKey: string, type: ArtType, url: string): Promise<{ ok: boolean; error?: string }> => {
      try {
        const dir = gameDir(consoleKey, slug);
        mkdirSync(dir, { recursive: true });
        await download(url, join(dir, `${type}.png`));
        return { ok: true };
      } catch (e: any) {
        return { ok: false, error: e.message || "Failed to save artwork" };
      }
    },
  );

  ipcMain.handle(
    "artwork:clearArt",
    async (_event, slug: string, consoleKey: string, type: ArtType): Promise<{ ok: boolean }> => {
      try {
        const dest = join(gameDir(consoleKey, slug), `${type}.png`);
        if (existsSync(dest)) unlinkSync(dest);
        return { ok: true };
      } catch {
        return { ok: false };
      }
    },
  );

  ipcMain.handle(
    "artwork:getCurrent",
    async (_event, slug: string, consoleKey: string): Promise<Record<ArtType, string | null>> => {
      const dir = gameDir(consoleKey, slug);
      const result = {} as Record<ArtType, string | null>;
      for (const type of ART_TYPES) {
        const dest = join(dir, `${type}.png`);
        result[type] = existsSync(dest) ? toDataUrl(dest) : null;
      }
      return result;
    },
  );

  ipcMain.handle(
    "artwork:refreshAll",
    async (
      _event, slug: string, gameName: string, consoleKey: string, sgdbGameId: number | null,
    ): Promise<Record<ArtType, boolean>> => {
      const result = {} as Record<ArtType, boolean>;
      const key = await getSteamGridDbKey();
      if (!key) {
        for (const type of ART_TYPES) result[type] = false;
        return result;
      }
      try {
        const client = makeSteamGridDbClient(key);
        let resolvedId = sgdbGameId;
        if (!resolvedId) {
          const games = await client.searchGame(gameName);
          resolvedId = games.length ? games[0].id : null;
        }
        if (!resolvedId) {
          for (const type of ART_TYPES) result[type] = false;
          return result;
        }
        const dir = gameDir(consoleKey, slug);
        mkdirSync(dir, { recursive: true });
        for (const type of ART_TYPES) {
          try {
            const images = await getSgdbImagesForType(client, resolvedId, type);
            if (!images.length) { result[type] = false; continue; }
            await download(String(images[0].url), join(dir, `${type}.png`));
            result[type] = true;
          } catch {
            result[type] = false;
          }
        }
        return result;
      } catch {
        for (const type of ART_TYPES) result[type] = false;
        return result;
      }
    },
  );
}
