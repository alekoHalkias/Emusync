// Pure helpers for the import wizard — no React, no IPC, no network.
// Kept side-effect-free so they're trivially unit-testable.
import type { Game, GameOverview } from "../../api";
import type { ConsoleOption, Phase, RomEntry } from "./types";

export const STEP_LABELS = ["Console", "Emulator", "ROMs"];

// Consoles whose save (and save states) live in ONE shared location across every
// game on the console — PS2's memory card + sstates folder (issues #294/#295).
// For these the per-game on-disk save/state must never be renamed, moved, or
// pushed per-game; the shared card/states are synced by `emusync run`. Accepts a
// console key ("ps2") or stored abbreviation ("PS2").
const _SHARED_SAVE_LAYOUT = new Set(["ps2"]);
export function usesSharedSaveLayout(consoleKeyOrAbbr: string): boolean {
  return _SHARED_SAVE_LAYOUT.has((consoleKeyOrAbbr || "").toLowerCase());
}

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

/**
 * Filesystem-safe version of a display title (issue #283): strip characters
 * illegal on Windows/POSIX (`<>:"/\|?*` + control chars), collapse runs of
 * whitespace, and trim. Falls back to the original (trimmed) title when the
 * result is empty so we never produce a blank filename.
 */
export function sanitizeFilename(title: string): string {
  const cleaned = title
    // eslint-disable-next-line no-control-regex
    .replace(/[<>:"/\\|?*\x00-\x1f]/g, "")
    .replace(/\s+/g, " ")
    .replace(/[. ]+$/, "")   // no trailing dots/spaces (Windows)
    .trim();
  return cleaned || title.trim();
}

/** Replace underscores with spaces and tidy whitespace (issue #283 bulk tool). */
export function replaceUnderscores(title: string): string {
  return title.replace(/_/g, " ").replace(/\s+/g, " ").trim();
}

/** Escape a literal string for use inside a RegExp. */
function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Case-insensitive, global, literal find/replace over a title (issue #283
 * find-and-replace tool). An empty `find` returns the title unchanged.
 */
export function findReplace(title: string, find: string, replacement: string): string {
  if (!find) return title;
  return title.replace(new RegExp(escapeRegExp(find), "gi"), replacement);
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

/** True if `p` is `root` or sits underneath it (slash-normalized). */
function underRoot(p: string, root: string): boolean {
  if (!root) return false;
  const n = p.replace(/\/$/, "");
  const r = root.replace(/\/$/, "");
  return n === r || n.startsWith(r + "/");
}

/**
 * Network-import classification (issue #270). Given ROMs scanned across the
 * network share root(s) and the console's local-copy folder, tag each as
 * "network" (only on the share), "local" (only on local disk), or "both" (on the
 * share with a local copy present). The same game found under both roots merges
 * into ONE "both" entry (matched by filename), keyed off the network copy as the
 * master with `localRomPath` pointing at the local copy.
 */
export function classifyByRoot(
  roms: RomEntry[],
  _networkRoots: string[],
  localRoot: string,
): RomEntry[] {
  const lRoot = localRoot.replace(/\/$/, "");
  const byKey = new Map<string, { network?: RomEntry; local?: RomEntry }>();
  for (const rom of roms) {
    const key = (rom.romPath.split("/").pop() || rom.romPath).toLowerCase();
    const slot = byKey.get(key) ?? {};
    // A ROM under the local root is the local copy; otherwise treat it as
    // network (covers both an explicit network root and the auto-detected dirs).
    if (lRoot && underRoot(rom.romPath, lRoot)) slot.local = rom;
    else slot.network = rom;
    byKey.set(key, slot);
  }
  const out: RomEntry[] = [];
  for (const { network, local } of byKey.values()) {
    if (network && local) out.push({ ...network, presence: "both", localRomPath: local.romPath });
    else if (network)     out.push({ ...network, presence: "network" });
    else if (local)       out.push({ ...local, presence: "local", localRomPath: local.romPath });
  }
  return out;
}

/**
 * Existing local-source library games for a console that should be copied UP to
 * the share during a network import (issue #281). Returns one `RomEntry` per
 * already-imported local game (tagged `presence: "local"`, `existingLocal`, and
 * `linkedSlug` so `_runImport` converts it in place instead of creating a
 * duplicate). Games already represented in `alreadyListed` (matched by ROM path)
 * are skipped so they aren't double-listed.
 */
export function existingLocalGamesForConsole(
  overview: GameOverview[],
  consoleAbbr: string,
  alreadyListed: RomEntry[],
): RomEntry[] {
  const listedPaths = new Set<string>();
  for (const r of alreadyListed) {
    if (r.romPath) listedPaths.add(r.romPath);
    if (r.localRomPath) listedPaths.add(r.localRomPath);
  }
  return overview
    .filter(o =>
      o.is_local &&
      o.rom_source === "local" &&
      o.console === consoleAbbr &&
      o.rom_path &&
      !listedPaths.has(o.rom_path),
    )
    .map(o => ({
      name: o.name,
      romPath: o.rom_path,
      romFileName: o.rom_path.split("/").pop() || o.rom_path,
      savePath: o.save_path,
      saveExists: false,
      launchCommand: o.launch_command,
      statePath: o.state_path,
      romFolderPath: o.rom_folder_path,
      linkedSlug: o.slug,
      presence: "local" as const,
      localRomPath: o.rom_path,
      existingLocal: true,
    }));
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
