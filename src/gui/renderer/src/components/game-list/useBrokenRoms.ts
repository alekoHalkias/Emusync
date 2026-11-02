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
    ...(c.device_extra_folders ?? []).map((folder) => ({ source: "local" as const, folder })),
    { source: "network" as const, folder: c.device_network_folder ?? "" },
  ].filter((x) => inside(x.folder, romPath));
  candidates.sort((a, b) => b.folder.length - a.folder.length);
  return candidates[0] ?? null;
}

export async function isRomMissing(g: GameRow): Promise<boolean> {
  if (!g.isLocal || g.romSource === "network" || !g.romPath) return false;
  return !(await window.emusync.files.exists(g.romPath));
}

/** A filename + size match awaiting confirmation (#731): a network game to link, or a moved local ROM to re-point. */
export type MatchProposal = { slug: string; romPath: string; kind: "network" | "relink"; mountRoot?: string };

/** This console's folders on this device, in sourceFor's order. */
const consoleFolders = (c: DeviceConsole): string[] =>
  [c.device_game_folder, ...(c.device_extra_folders ?? []), c.device_local_folder ?? "", c.device_network_folder ?? ""].filter(Boolean);

/** A local-source game Refresh offers to move into the console folder and/or add to the network drive (#626). */
export type LocalCandidate = { game: GameRow; folder: string; netFolder: string; canMove: boolean; canUpload: boolean };

export function useBrokenRoms(games: GameRow[]) {
  const [broken, setBroken] = useState<Set<string>>(new Set());

  async function refresh(deviceId?: string): Promise<{ missing: number; corrected: number; candidates: LocalCandidate[]; proposals: MatchProposal[] }> {
    const missing = await Promise.all(games.map(isRomMissing));
    const next = new Set(games.filter((_, i) => missing[i]).map((g) => g.slug));
    setBroken(next);
    let corrected = 0;
    const candidates: LocalCandidate[] = [];
    const proposals: MatchProposal[] = [];
    const consoles = deviceId ? await getDeviceConsoles(deviceId).catch(() => [] as DeviceConsole[]) : [];
    for (const g of games) {
      const c = consoles.find((x) => x.console_name.toLowerCase() === (g.console ?? "").toLowerCase());
      // A moved ROM: same filename + size in one of the console's folders, proposed for confirmation (#731).
      if (c && next.has(g.slug) && g.romPath && (g.romSize ?? 0) > 0) {
        const hit = await window.emusync.rom.findByNameSize(consoleFolders(c), g.romPath, g.romSize!).catch(() => null);
        if (hit) proposals.push({ slug: g.slug, romPath: hit, kind: "relink" });
      }
      if (!g.isLocal || !g.romPath || next.has(g.slug)) continue;
      // Rows from before #731 carry no size, so they can never be matched; record it once (best effort).
      if (!g.romSize) {
        const size = await window.emusync.files.size(g.romPath).catch(() => 0);
        if (size > 0) await getGameDevice(g.slug).then((cfg) => setGameDevice(g.slug, { ...cfg, rom_size: size })).catch(() => {});
      }
      if (!c) continue;
      const hit = sourceFor(g.romPath, c);
      const folder = c.device_local_folder ?? "";
      const netFolder = c.device_network_folder ?? "";
      if ((!hit || hit.source === "local") && (g.romSource ?? "local") === "local") {
        const canMove = !!folder && !inside(folder, g.romPath);
        if (canMove || netFolder) candidates.push({ game: g, folder, netFolder, canMove, canUpload: !!netFolder });
      }
      if (!hit || hit.source === (g.romSource ?? "local")) continue;
      try {
        const cfg = await getGameDevice(g.slug);
        const rel = norm(g.romPath).slice(norm(hit.folder).replace(/\/+$/, "").length + 1);
        await setGameDevice(g.slug, { ...cfg, rom_source: hit.source, ...(hit.source === "network" ? { rom_rel_path: rel } : {}) });
        corrected++;
      } catch { /* leave this game unchanged */ }
    }
    return { missing: next.size, corrected, candidates, proposals };
  }

  /** Point `game` at `newPath`, remember its folder, then fix sibling broken games. Returns how many others were fixed. */
  async function relink(game: GameRow, newPath: string): Promise<number> {
    await updateRom(game.slug, newPath);
    const folder = dirname(newPath);
    if (game.console) await window.emusync.config.addRecentFolder(game.console, folder).catch(() => {});
    // ponytail: probes the same filename in the new folder and its parent instead of a full emulator:scan; renamed ROMs are not matched.
    // A known size must also match, so a different dump with the same name is not adopted (#731).
    let fixed = 0;
    const done = new Set([game.slug]);
    for (const other of games) {
      if (other.console !== game.console || !other.romPath || !(await isRomMissing(other))) continue;
      for (const dir of [folder, dirname(folder)]) {
        const candidate = `${dir}/${basename(other.romPath)}`;
        if (dir && (await window.emusync.files.exists(candidate))
            && (!other.romSize || (await window.emusync.files.size(candidate)) === other.romSize)) {
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

export async function updateRom(slug: string, romPath: string): Promise<void> {
  const cfg = await getGameDevice(slug);
  const size = await window.emusync.files.size(romPath).catch(() => 0);
  await setGameDevice(slug, { ...cfg, rom_path: romPath, ...(size > 0 ? { rom_size: size } : {}) });
}
