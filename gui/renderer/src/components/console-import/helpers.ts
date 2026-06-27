// Pure helpers for the import wizard — no React, no IPC, no network.
// Kept side-effect-free so they're trivially unit-testable.
import type { Game } from "../../api";
import type { ConsoleOption, Phase, RomEntry } from "./types";

export const STEP_LABELS = ["Console", "Emulator", "ROMs"];

export function stepIndex(phase: Phase): number {
  if (phase === "console" || phase === "detecting") return 0;
  if (phase === "emulator") return 1;
  return 2;
}

/**
 * The console's stored abbreviation (used as the game's `console` value),
 * derived from the defs fetched from the server (which carry `abbr`) rather
 * than a hardcoded map. Falls back to the upper-cased key.
 */
export function getConsoleAbbreviation(consoleKey: string, consoles: ConsoleOption[]): string {
  return consoles.find(c => c.key === consoleKey)?.abbr || consoleKey.toUpperCase();
}

/** ROM filename without extension, lowercased (used for fuzzy matching). */
export function getRomFileName(path: string): string {
  const filename = path.split("/").pop() || "";
  return filename.replace(/\.[^.]+$/, "").toLowerCase();
}

/** Slugify an already-lowercased string (callers lowercase first). */
export function slugify(s: string): string {
  return s.replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

/**
 * Decide which source folder a ROM came from: a selected path first, then a
 * scan-result dir, then the ROM's own parent directory as a last resort.
 */
export function resolveRomFolder(romPath: string, selectedPaths: string[], scanRomDirs: string[]): string {
  const normalizedRom = romPath.replace(/\/$/, "");

  for (const path of selectedPaths) {
    const normalizedPath = path.replace(/\/$/, "");
    if (normalizedRom.startsWith(normalizedPath + "/") || normalizedRom === normalizedPath) {
      return normalizedPath;
    }
  }

  for (const dir of scanRomDirs) {
    const normalizedDir = dir.replace(/\/$/, "");
    if (normalizedRom.startsWith(normalizedDir + "/") || normalizedRom === normalizedDir) {
      return normalizedDir;
    }
  }

  return romPath.replace(/[^/]+$/, "").replace(/\/$/, "") || "/";
}

/** Add `romFileName` + `romFolderPath` to each scanned ROM. */
export function annotateRoms(scanRoms: RomEntry[], selectedPaths: string[], scanRomDirs: string[]): RomEntry[] {
  return scanRoms.map(rom => ({
    ...rom,
    romFileName: getRomFileName(rom.romPath),
    romFolderPath: resolveRomFolder(rom.romPath, selectedPaths, scanRomDirs),
  }));
}

/**
 * Tag each ROM as already-on-this-device (filtered out) or cross-device link
 * (tagged with `linkedSlug`/`linkedName`). Returns the displayable ROMs plus
 * how many were skipped as already imported here.
 */
export function dedupeAndLink(
  annotated: RomEntry[],
  existingGames: Game[],
  thisDeviceConfigs: Array<{ slug: string; romPath: string }>,
): { roms: RomEntry[]; skipCount: number } {
  const withMatches = annotated.map(rom => {
    // 1. Already on this device → skip
    const thisMatch = thisDeviceConfigs.find(cfg =>
      cfg.romPath === rom.romPath || getRomFileName(cfg.romPath) === rom.romFileName
    );
    if (thisMatch) return { ...rom, existingGameSlug: thisMatch.slug };

    // 2. Exists on another device → link candidate (match by slug or name)
    const slugified = slugify(rom.romFileName);
    const crossMatch = existingGames.find(g => {
      const nameSlug = slugify(g.name.toLowerCase());
      return g.slug === slugified || nameSlug === slugified ||
        g.name.toLowerCase() === rom.name.toLowerCase();
    });
    if (crossMatch) return { ...rom, linkedSlug: crossMatch.slug, linkedName: crossMatch.name };

    return rom;
  });

  const roms = withMatches.filter(rom => !rom.existingGameSlug);
  return { roms, skipCount: withMatches.length - roms.length };
}

/**
 * POSIX relative path of `romPath` under whichever scan `root` contains it,
 * for portable network-ROM storage (issue #255). Falls back to the basename
 * when no root matches.
 */
export function relPathUnder(romPath: string, roots: string[]): string {
  const norm = romPath.replace(/\/$/, "");
  for (const root of roots) {
    const r = root.replace(/\/$/, "");
    if (norm === r) break;
    if (norm.startsWith(r + "/")) return norm.slice(r.length + 1);
  }
  return norm.split("/").pop() || norm;
}

/** Group ROMs by their parent directory (for the results list headers). */
export function groupByDir(roms: RomEntry[]): Record<string, RomEntry[]> {
  const grouped: Record<string, RomEntry[]> = {};
  for (const rom of roms) {
    const dir = rom.romPath.replace(/[^/]+$/, "").replace(/\/$/, "") || "/";
    (grouped[dir] = grouped[dir] ?? []).push(rom);
  }
  return grouped;
}
