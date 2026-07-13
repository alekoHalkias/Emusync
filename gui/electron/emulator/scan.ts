// ROM directory scanning and save/state path resolution for the import wizard.
import { existsSync, readdirSync } from "fs";
import { join, basename, extname, dirname } from "path";
import { rt } from "../runtime";
import { findLatestFileInDir } from "../files";
import { ROM_EXTENSIONS, DEFAULT_SAVE_EXTS, RomEntry, EmulatorScanResult, DetectedEmulatorOption } from "./types";

// Consoles whose save is a single card/folder shared across every game on the
// console, reconciled per-console — not per-game — by `emusync run` (#295):
// PS2 memory card, Dreamcast VMU, Dolphin GC cards, PPSSPP SAVEDATA (#402).
// Keep in sync with run_ps2.py's _SHARED_MEMCARD_CONSOLES and
// console-import/helpers.ts's _SHARED_SAVE_LAYOUT.
const SHARED_MEMCARD_CONSOLES = new Set(["ps2", "dc", "gamecube", "psp"]);
// Consoles whose save STATES are also shared (PS2's serial-named sstates/) —
// dc/gamecube/psp cores write normal per-content RetroArch states.
const SHARED_STATE_CONSOLES = new Set(["ps2"]);

/** Resolve the shared card path for a shared-save console: the first existing
 *  candidate, else the canonical default (registered before it exists). */
function resolveSharedCard(consoleKey: string, saveDir: string, saveRoot: string, systemDir?: string): string {
  if (consoleKey === "ps2") {
    // Scan the memcards dir for the first .ps2 entry (file or folder); fall
    // back to Mcd001.ps2 (issue #314).
    return findFirstByExt(saveRoot, ".ps2") ?? join(saveRoot, "Mcd001.ps2");
  }
  let candidates: string[] = [];
  if (consoleKey === "dc") {
    // Flycast writes shared VMUs to the frontend save dir. ponytail: only VMU
    // slot A1 is synced — B1/A2 (2nd controller / extra cards) are rare.
    candidates = [join(saveRoot, "vmu_save_A1.bin"), join(saveDir, "vmu_save_A1.bin")];
  } else if (consoleKey === "gamecube") {
    // Dolphin core's GC memory-card folder. ponytail: Wii NAND title saves are
    // NOT synced (large tree mixing system data) — follow-up if wanted.
    candidates = [join(saveRoot, "User", "GC"), join(saveDir, "User", "GC")];
    if (systemDir) candidates.push(join(systemDir, "dolphin-emu", "Userdata", "GC"));
  } else if (consoleKey === "psp") {
    // PPSSPP keeps all games' savedata under one folder — synced as one
    // console-wide card. ponytail: per-game granularity needs serial parsing.
    candidates = [join(saveRoot, "PPSSPP", "PSP", "SAVEDATA"), join(saveDir, "PSP", "SAVEDATA")];
  }
  return candidates.find(p => existsSync(p)) ?? candidates[0] ?? saveRoot;
}

/** Scan dir for the first entry (file or folder) ending in ext; returns its full path or null. */
function findFirstByExt(dir: string, ext: string): string | null {
  try {
    const entries = readdirSync(dir, { withFileTypes: true });
    for (const e of entries) {
      if (e.name.toLowerCase().endsWith(ext)) return join(dir, e.name);
    }
  } catch { /* unreadable dir */ }
  return null;
}

function scanRomDir(dir: string, depth = 0): string[] {
  if (depth > 3) return [];
  try {
    const entries = readdirSync(dir, { withFileTypes: true });
    const roms: string[] = [];
    for (const e of entries) {
      if (e.isFile() && ROM_EXTENSIONS.has(extname(e.name).slice(1).toLowerCase())) {
        roms.push(join(dir, e.name));
      } else if (e.isDirectory()) {
        roms.push(...scanRomDir(join(dir, e.name), depth + 1));
      }
    }
    return roms;
  } catch { return []; }
}

/** Search saveDir for a file matching baseName + any of the given extensions. */
function matchSaveFile(saveDir: string, baseName: string, exts: string[]): { path: string; exists: boolean } {
  for (const ext of exts) {
    const p = join(saveDir, `${baseName}.${ext}`);
    if (existsSync(p)) return { path: p, exists: true };
  }
  return { path: join(saveDir, `${baseName}.${exts[0]}`), exists: false };
}

export function runEmulatorScan(params: {
  consoleKey: string;
  emulatorOption: DetectedEmulatorOption;
  extraPaths: string[];
}): EmulatorScanResult {
  const { consoleKey, emulatorOption, extraPaths } = params;
  console.error(`[scan] consoleKey=${consoleKey} extraPaths=${JSON.stringify(extraPaths)} emulatorRomDirs=${JSON.stringify(emulatorOption.romDirs)}`);

  const consoleDef = rt.cachedConsoleDefs?.[consoleKey];
  if (!consoleDef) {
    console.error(`[scan] ERROR: unknown consoleKey '${consoleKey}'`);
    return { emulators: [], romDirs: [], roms: [] };
  }

  // Scannable extensions: a console's explicit romExtensions when set (decoupled
  // from core-derived systemKeys so a standalone-only console like PS2 scans the
  // right files), else fall back to systemKeys (issue #293).
  const romExts: string[] = (consoleDef.romExtensions?.length ? consoleDef.romExtensions : consoleDef.systemKeys) ?? [];
  const romExtSet = new Set(romExts);
  const romDirs = [...new Set([...emulatorOption.romDirs, ...(extraPaths ?? [])].filter(Boolean))];
  console.error(`[scan] romExtSet=${JSON.stringify([...romExtSet])} romDirs=${JSON.stringify(romDirs)}`);

  const firstSys = rt.cachedSystemDefs?.[consoleDef.systemKeys[0]];
  const defaultSaveExts = firstSys?.saveExts ?? DEFAULT_SAVE_EXTS;

  const roms: RomEntry[] = romDirs.flatMap(dir => {
    const allInDir = scanRomDir(dir);
    console.error(`[scan] dir='${dir}' → scanRomDir found ${allInDir.length} files total`);
    const filtered = allInDir.filter(p => romExtSet.has(extname(p).slice(1).toLowerCase()));
    console.error(`[scan] dir='${dir}' → after ext filter (${[...romExtSet].join(",")}) kept ${filtered.length}`);
    return filtered
      .map(romPath => {
        const romExt = extname(romPath).slice(1).toLowerCase();
        const base   = basename(romPath, extname(romPath));
        const system = rt.cachedSystemDefs?.[romExt];
        const saveExts = system?.save_exts ?? defaultSaveExts;

        // When a ROM lives in a per-game subfolder (e.g. roms/GBA/GameName/game.gba)
        // RetroArch's "Sort saves/states by content directory" option mirrors that
        // subfolder name into saves/ and states/ WITHOUT the core name subfolder:
        //   saves/GameName/game.srm  or  states/GameName/game.state
        // We must check those paths in addition to the core-subfolder patterns.
        const romParentDir    = dirname(romPath);
        const contentSubfolder = romParentDir !== dir ? basename(romParentDir) : null;
        const saveRoot  = emulatorOption.coreFolderName ? dirname(emulatorOption.saveDir)  : emulatorOption.saveDir;

        // ── Save file lookup (single file) ────────────────────────────────────
        // Priority: content-dir path first, then legacy core-subfolder / flat root.
        // Target path: savesRoot/GameName/GameName.ext  (no core-name layer)
        const gameFolderName = contentSubfolder ?? base;
        const isSharedMemcard = SHARED_MEMCARD_CONSOLES.has(consoleKey);
        let m: { path: string; exists: boolean };
        if (isSharedMemcard) {
          // Shared-save console: every game's savePath is the same card (#295/#402).
          const cardPath = resolveSharedCard(consoleKey, emulatorOption.saveDir, saveRoot, emulatorOption.systemDir);
          m = { path: cardPath, exists: existsSync(cardPath) };
        } else {
          m = matchSaveFile(join(saveRoot, gameFolderName), base, saveExts);
          if (!m.exists) {
            // saves/mGBA/GameName/base.ext  (core + content-dir)
            const mCC = matchSaveFile(join(emulatorOption.saveDir, gameFolderName), base, saveExts);
            if (mCC.exists) m = mCC;
          }
          if (!m.exists) {
            // saves/mGBA/base.ext  (core only, legacy flat)
            const mFlat = matchSaveFile(emulatorOption.saveDir, base, saveExts);
            if (mFlat.exists) m = mFlat;
          }
          if (!m.exists && emulatorOption.coreFolderName) {
            // saves/base.ext  (legacy flat root)
            const mRoot = matchSaveFile(saveRoot, base, saveExts);
            if (mRoot.exists) m = mRoot;
          }
          // Always register the canonical target path (savesRoot/GameName/base.ext)
          // so the path is correct even before RetroArch creates the file.
          if (!m.exists) {
            m = { path: join(saveRoot, gameFolderName, `${base}.${saveExts[0]}`), exists: false };
          }
        }

        // ── State folder lookup ────────────────────────────────────────────────
        // state_path stores the FOLDER (statesRoot/GameName/) because multiple
        // state slots coexist there. We check whether it already has any files.
        let sm: { path: string; exists: boolean } | undefined;
        if (emulatorOption.stateDir) {
          const stateRoot = emulatorOption.coreFolderName ? dirname(emulatorOption.stateDir) : emulatorOption.stateDir;
          if (SHARED_STATE_CONSOLES.has(consoleKey)) {
            // Shared sstates folder (PS2): every game's states live flat in one
            // folder, named per serial — point at the folder itself; `emusync run`
            // syncs only this game's serial files (issue #294). dc/gamecube/psp
            // cores write normal per-content states, so they take the else branch.
            sm = { path: stateRoot, exists: !!findLatestFileInDir(stateRoot) };
          } else {
            const stateFolder = join(stateRoot, gameFolderName);
            sm = { path: stateFolder, exists: !!findLatestFileInDir(stateFolder) };
          }
        }

        const standaloneArgs = (emulatorOption.launchArgs ?? []).join(" ");
        const launchCommand = emulatorOption.corePath
          ? `${emulatorOption.execPath} -L "${emulatorOption.corePath}" "${romPath}"`
          : `${emulatorOption.execPath}${standaloneArgs ? ` ${standaloneArgs}` : ""} "${romPath}"`;
        return {
          name: base, romPath,
          savePath: m.path, saveExists: m.exists,
          statePath: sm?.path, stateExists: sm?.exists,
          launchCommand,
          consoleName: system?.name ?? consoleDef.label,
          coreName: emulatorOption.coreFolderName,
        };
      });
  });

  console.error(`[scan] total ROMs returning to renderer: ${roms.length}`);
  return {
    emulators: [{ type: "native" as const, label: emulatorOption.label,
      execPath: emulatorOption.execPath, saveDir: emulatorOption.saveDir,
      statesDir: emulatorOption.stateDir ?? "", coresDir: "", infoDirs: [], romDirs: emulatorOption.romDirs }],
    romDirs,
    roms,
  };
}
