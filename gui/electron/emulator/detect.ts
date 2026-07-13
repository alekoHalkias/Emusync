// RetroArch + standalone emulator detection for a given console.
import { existsSync, readFileSync, readdirSync } from "fs";
import { execSync } from "child_process";
import { join } from "path";
import { rt } from "../runtime";
import type { EmulatorInfo, DetectedEmulatorOption, StandaloneDef } from "./types";

export function parseRetroArchCfg(cfgPath: string, home: string): Record<string, string> {
  const out: Record<string, string> = {};
  if (!existsSync(cfgPath)) return out;
  // Node.js doesn't expand ~ — do it here so all path fields are absolute
  const expandHome = (v: string) => v.startsWith("~/") ? join(home, v.slice(2)) : v === "~" ? home : v;
  for (const line of readFileSync(cfgPath, "utf-8").split("\n")) {
    const m = line.match(/^\s*(\w+)\s*=\s*"?([^"#\r\n]*)"?\s*$/);
    if (m) out[m[1].trim()] = expandHome(m[2].trim());
  }
  return out;
}

/** Candidate dirs for core .info metadata files, best source first (#400). */
function infoDirCandidates(cfg: Record<string, string>, coresDir: string): string[] {
  return [...new Set([cfg.libretro_info_path, coresDir, "/usr/share/libretro/info"].filter(Boolean))] as string[];
}

export function detectRetroArch(home: string): EmulatorInfo[] {
  const infos: EmulatorInfo[] = [];

  // ── native ──────────────────────────────────────────────────────────────────
  const nativeBins = ["/usr/bin/retroarch", "/usr/local/bin/retroarch", join(home, ".local/bin/retroarch")];
  const nativeCfg  = join(home, ".config/retroarch/retroarch.cfg");
  for (const bin of nativeBins) {
    if (existsSync(bin)) {
      const cfg = parseRetroArchCfg(nativeCfg, home);
      // Filter out RetroArch's "default" placeholder (means "not configured")
      const romDir = cfg.rgui_browser_directory && cfg.rgui_browser_directory !== "default"
        ? cfg.rgui_browser_directory : "";
      const coresDir = cfg.libretro_directory || join(home, ".config/retroarch/cores");
      infos.push({
        type:     "native",
        label:    "RetroArch",
        execPath:  bin,
        saveDir:   cfg.savefile_directory || join(home, ".config/retroarch/saves"),
        statesDir: cfg.savestate_directory || join(home, ".config/retroarch/states"),
        coresDir,
        infoDirs: infoDirCandidates(cfg, coresDir),
        systemDir: cfg.system_directory || join(home, ".config/retroarch/system"),
        romDirs:  [romDir].filter(Boolean) as string[],
      });
      break;
    }
  }

  // ── flatpak ─────────────────────────────────────────────────────────────────
  try {
    const list = execSync("flatpak list --app --columns=application 2>/dev/null", { timeout: 5000 }).toString();
    if (list.includes("org.libretro.RetroArch")) {
      const flatCfg = join(home, ".var/app/org.libretro.RetroArch/config/retroarch/retroarch.cfg");
      const cfg = parseRetroArchCfg(flatCfg, home);
      const flatRomDir = cfg.rgui_browser_directory && cfg.rgui_browser_directory !== "default"
        ? cfg.rgui_browser_directory : "";
      const coresDir = cfg.libretro_directory || join(home, ".var/app/org.libretro.RetroArch/data/retroarch/cores");
      infos.push({
        type:     "flatpak",
        label:    "RetroArch (Flatpak)",
        execPath: "flatpak run org.libretro.RetroArch",
        saveDir:  cfg.savefile_directory || join(home, ".var/app/org.libretro.RetroArch/config/retroarch/saves"),
        statesDir: cfg.savestate_directory || join(home, ".var/app/org.libretro.RetroArch/config/retroarch/states"),
        coresDir,
        infoDirs: infoDirCandidates(cfg, coresDir),
        systemDir: cfg.system_directory || join(home, ".var/app/org.libretro.RetroArch/config/retroarch/system"),
        romDirs:  [flatRomDir].filter(Boolean) as string[],
      });
    }
  } catch { /* flatpak not available */ }

  return infos;
}

/** Every installed core for a system in the given coresDir, in list order —
 *  all of them, not just the first, so alternate cores show as options (#400). */
function findInstalledCores(coresDir: string, system: any): Array<{ lib: string; folderName: string }> {
  const found: Array<{ lib: string; folderName: string }> = [];
  for (const core of system.cores || []) {
    const libName = core.libName || core.lib;
    const folderName = core.folderName || core.folder;
    const soPath = join(coresDir, `${libName}.so`);
    if (existsSync(soPath)) found.push({ lib: soPath, folderName });
  }
  return found;
}

/** Discover installed cores for a console from RetroArch's own .info metadata
 *  (#400): each core ships a `<lib>.info` whose `database` field names the
 *  systems it runs (pipe-separated libretro database names) and whose
 *  `corename` is the exact name RetroArch uses for `saves/<CoreName>/`.
 *  Matching that against the console def's `databases` recognizes ANY core for
 *  a supported console — including ones not in the hardcoded seed lists. */
function discoverCoresByInfo(
  coresDir: string, infoDirs: string[], databases: string[], home: string,
): Array<{ lib: string; folderName: string }> {
  if (!databases.length || !existsSync(coresDir)) return [];
  const wanted = new Set(databases);
  const found: Array<{ lib: string; folderName: string }> = [];
  let soFiles: string[];
  try { soFiles = readdirSync(coresDir).filter((f) => f.endsWith(".so")).sort(); }
  catch { return []; }
  for (const so of soFiles) {
    const base = so.slice(0, -3); // strip ".so"
    const infoPath = infoDirs.map((d) => join(d, `${base}.info`)).find((p) => existsSync(p));
    if (!infoPath) continue;
    const info = parseRetroArchCfg(infoPath, home); // same key = "value" format
    if (!info.corename || !(info.database || "").split("|").some((db) => wanted.has(db.trim()))) continue;
    found.push({ lib: join(coresDir, so), folderName: info.corename });
  }
  return found;
}

function findConsoleRomDirs(baseDir: string, consoleKey: string): string[] {
  if (!baseDir || !existsSync(baseDir)) return [];

  const folderNames = rt.cachedConsoleFolderNames?.[consoleKey] ?? [consoleKey.toUpperCase()];
  const results: string[] = [];

  try {
    const entries = readdirSync(baseDir, { withFileTypes: true });
    for (const entry of entries) {
      if (!entry.isDirectory()) continue;
      const entryLower = entry.name.toLowerCase();
      for (const pattern of folderNames) {
        if (entryLower === pattern.toLowerCase()) {
          results.push(join(baseDir, entry.name));
          break;
        }
      }
    }
  } catch { /* ignore read errors */ }

  return results;
}

export function detectEmulatorsForConsole(home: string, consoleKey: string): DetectedEmulatorOption[] {
  const consoleDef = rt.cachedConsoleDefs?.[consoleKey];
  if (!consoleDef) return [];
  const options: DetectedEmulatorOption[] = [];

  // ── RetroArch (native + flatpak) ──────────────────────────────────────────
  for (const ra of detectRetroArch(home)) {
    // Every installed core for this console: the seeded core lists first
    // (preferred order), then any extra cores discovered via .info metadata —
    // so an unlisted-but-valid core (e.g. a brand-new SNES core) still shows
    // up with the right save folder (#400).
    const cores: Array<{ lib: string; folderName: string }> = [];
    const seenCores = new Set<string>();
    const addCore = (core: { lib: string; folderName: string }) => {
      if (seenCores.has(core.lib)) return;
      seenCores.add(core.lib);
      cores.push(core);
    };
    for (const sysKey of consoleDef.systemKeys) {
      const sys = rt.cachedSystemDefs?.[sysKey];
      if (sys) findInstalledCores(ra.coresDir, sys).forEach(addCore);
    }
    discoverCoresByInfo(ra.coresDir, ra.infoDirs, consoleDef.databases ?? [], home).forEach(addCore);

    // Try to find console-specific ROM subfolders first
    let romDirs = ra.romDirs;
    if (ra.romDirs.length > 0) {
      const consoleDirs = findConsoleRomDirs(ra.romDirs[0], consoleKey);
      if (consoleDirs.length > 0) {
        romDirs = consoleDirs;
      }
    }

    for (const core of cores) {
      options.push({
        id: `${ra.type}-${core.folderName.toLowerCase().replace(/[^a-z0-9]/g, "-")}`,
        label: `${ra.label} · ${core.folderName}`,
        execPath: ra.execPath,
        saveDir: join(ra.saveDir, core.folderName),
        stateDir: join(ra.statesDir, core.folderName),
        corePath: core.lib,
        coreFolderName: core.folderName,
        systemDir: ra.systemDir,
        romDirs,
      });
    }
  }

  // ── Standalone emulators ──────────────────────────────────────────────────
  let flatpakList: string | null = null;
  const getFlatpakList = () => {
    if (flatpakList !== null) return flatpakList;
    try { flatpakList = execSync("flatpak list --app --columns=application 2>/dev/null", { timeout: 5000 }).toString(); }
    catch { flatpakList = ""; }
    return flatpakList;
  };

  // Standalone defs come from the server as JSON (issue #292): snake_case fields,
  // `native_bins` is a string[], and `dirs` carries `~`-templated save/state/
  // memcard dirs per launch flavour. Expand `~` against this device's home.
  const expand = (p: string): string => !p ? p : p.startsWith("~/") ? join(home, p.slice(2)) : p === "~" ? home : p;
  for (const s of (consoleDef.standalones ?? []) as StandaloneDef[]) {
    const dirs = s.dirs ?? {};
    let found = false;
    for (const bin of s.native_bins ?? []) {
      if (existsSync(expand(bin))) {
        options.push({
          id: `${s.id}-native`, label: s.label, execPath: expand(bin),
          saveDir: expand(dirs.native?.save ?? s.save_dir_template ?? ""),
          stateDir: dirs.native?.state ? expand(dirs.native.state) : undefined,
          launchArgs: s.launch_args ?? [],
          romDirs: [],
        });
        found = true; break;
      }
    }
    if (!found && s.flatpak_id && s.flatpak_exec && getFlatpakList().includes(s.flatpak_id)) {
      options.push({
        id: `${s.id}-flatpak`, label: `${s.label} (Flatpak)`,
        execPath: s.flatpak_exec,
        saveDir: expand(dirs.flatpak?.save ?? ""),
        stateDir: dirs.flatpak?.state ? expand(dirs.flatpak.state) : undefined,
        launchArgs: s.launch_args ?? [],
        romDirs: [],
      });
    }
  }

  return options;
}
