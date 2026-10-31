// Per-console ROM ignore list for the import wizard (#646), kept in the config as
// `import_ignored_roms[consoleKey] = [romPath, ...]`.
import type { RomEntry } from "./types";

const emusync = window.emusync;

export async function loadIgnoredRoms(consoleKey: string): Promise<string[]> {
  const cfg = await emusync.config.load();
  return cfg?.import_ignored_roms?.[consoleKey] ?? [];
}

/** Replace a console's ignore list; an empty list removes its entry. */
export async function saveIgnoredRoms(consoleKey: string, paths: string[]): Promise<void> {
  const cfg = (await emusync.config.load()) ?? {};
  const all = { ...(cfg.import_ignored_roms ?? {}) };
  if (paths.length > 0) all[consoleKey] = paths;
  else delete all[consoleKey];
  cfg.import_ignored_roms = all;
  await emusync.config.save(cfg);
}

/** Drop scanned ROMs whose path is on the ignore list. */
export function filterIgnored(roms: RomEntry[], ignored: Set<string>): RomEntry[] {
  return ignored.size === 0 ? roms : roms.filter(r => !ignored.has(r.romPath));
}
