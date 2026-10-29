import { useState } from "react";
import { getGameDevice, setGameDevice } from "../../api";
import type { GameRow } from "./types";

// Broken-ROM detection and re-link (issue #616). Only local-source games are
// checked: network ROMs live on a drive that may just be unmounted.
const norm = (p: string): string => p.replace(/\\/g, "/");
const basename = (p: string): string => norm(p).split("/").filter(Boolean).pop() ?? p;
const dirname = (p: string): string => norm(p).replace(/\/[^/]*\/?$/, "");

export async function isRomMissing(g: GameRow): Promise<boolean> {
  if (!g.isLocal || g.romSource === "network" || !g.romPath) return false;
  return !(await window.emusync.files.exists(g.romPath));
}

export function useBrokenRoms(games: GameRow[]) {
  const [broken, setBroken] = useState<Set<string>>(new Set());

  async function refresh(): Promise<number> {
    const missing = await Promise.all(games.map(isRomMissing));
    const next = new Set(games.filter((_, i) => missing[i]).map((g) => g.slug));
    setBroken(next);
    return next.size;
  }

  /** Point `game` at `newPath`, remember its folder, then fix sibling broken games. Returns how many others were fixed. */
  async function relink(game: GameRow, newPath: string): Promise<number> {
    await updateRom(game.slug, newPath);
    const folder = dirname(newPath);
    if (game.console) await window.emusync.config.addRecentFolder(game.console, folder).catch(() => {});
    // ponytail: probes the same filename in the new folder and its parent instead of a full emulator:scan; renamed ROMs are not matched.
    let fixed = 0;
    const done = new Set([game.slug]);
    for (const other of games) {
      if (other.console !== game.console || !other.romPath || !(await isRomMissing(other))) continue;
      for (const dir of [folder, dirname(folder)]) {
        const candidate = `${dir}/${basename(other.romPath)}`;
        if (dir && (await window.emusync.files.exists(candidate))) {
          await updateRom(other.slug, candidate);
          done.add(other.slug);
          fixed++;
          break;
        }
      }
    }
    setBroken((prev) => new Set([...prev].filter((s) => !done.has(s))));
    return fixed;
  }

  return { broken, refresh, relink };
}

async function updateRom(slug: string, romPath: string): Promise<void> {
  const cfg = await getGameDevice(slug);
  await setGameDevice(slug, { ...cfg, rom_path: romPath });
}
