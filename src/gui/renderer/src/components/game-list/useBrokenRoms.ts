import { useState } from "react";
import { getDeviceConsoles, getGameDevice, setGameDevice, type DeviceConsole } from "../../api";
import type { GameRow } from "./types";

// Broken-ROM detection and re-link (issue #616). Only local-source games are
// checked: network ROMs live on a drive that may just be unmounted.
const norm = (p: string): string => p.replace(/\\/g, "/");
const basename = (p: string): string => norm(p).split("/").filter(Boolean).pop() ?? p;
const dirname = (p: string): string => norm(p).replace(/\/[^/]*\/?$/, "");

const inside = (folder: string, path: string): boolean => {
  const f = norm(folder).replace(/\/+$/, "");
  return !!f && norm(path).startsWith(f + "/");
};

/** Which source a ROM path belongs to per the console's folders (longest match wins), or null (issue #618). */
export function sourceFor(romPath: string, c: DeviceConsole): { source: "local" | "network"; folder: string } | null {
  const candidates = [
    { source: "local" as const, folder: c.device_local_folder ?? "" },
    { source: "local" as const, folder: c.device_game_folder },
    { source: "network" as const, folder: c.device_network_folder ?? "" },
  ].filter((x) => inside(x.folder, romPath));
  candidates.sort((a, b) => b.folder.length - a.folder.length);
  return candidates[0] ?? null;
}

export async function isRomMissing(g: GameRow): Promise<boolean> {
  if (!g.isLocal || g.romSource === "network" || !g.romPath) return false;
  return !(await window.emusync.files.exists(g.romPath));
}

export function useBrokenRoms(games: GameRow[]) {
  const [broken, setBroken] = useState<Set<string>>(new Set());

  async function refresh(deviceId?: string): Promise<{ missing: number; corrected: number }> {
    const missing = await Promise.all(games.map(isRomMissing));
    const next = new Set(games.filter((_, i) => missing[i]).map((g) => g.slug));
    setBroken(next);
    let corrected = 0;
    const consoles = deviceId ? await getDeviceConsoles(deviceId).catch(() => [] as DeviceConsole[]) : [];
    for (const g of games) {
      const c = consoles.find((x) => x.console_name.toLowerCase() === (g.console ?? "").toLowerCase());
      if (!c || !g.isLocal || !g.romPath || next.has(g.slug)) continue;
      const hit = sourceFor(g.romPath, c);
      if (!hit || hit.source === (g.romSource ?? "local")) continue;
      try {
        const cfg = await getGameDevice(g.slug);
        const rel = norm(g.romPath).slice(norm(hit.folder).replace(/\/+$/, "").length + 1);
        await setGameDevice(g.slug, { ...cfg, rom_source: hit.source, ...(hit.source === "network" ? { rom_rel_path: rel } : {}) });
        corrected++;
      } catch { /* leave this game unchanged */ }
    }
    return { missing: next.size, corrected };
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
          // Best effort: the primary re-link already succeeded, so a sibling failure must not abort the launch.
          if (await updateRom(other.slug, candidate).then(() => true, () => false)) { done.add(other.slug); fixed++; }
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
