// ROM directory scanning and save/state path resolution for the import wizard.
import { existsSync, readdirSync } from "fs";
import { join, basename, extname, dirname } from "path";
import { rt } from "../runtime";
import { findLatestFileInDir } from "../files";
import { ROM_EXTENSIONS, DEFAULT_SAVE_EXTS, RomEntry, EmulatorScanResult, DetectedEmulatorOption } from "./types";

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

  const romExtSet = new Set(consoleDef.systemKeys);
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
        let m = matchSaveFile(join(saveRoot, gameFolderName), base, saveExts);
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

        // ── State folder lookup ────────────────────────────────────────────────
        // state_path stores the FOLDER (statesRoot/GameName/) because multiple
        // state slots coexist there. We check whether it already has any files.
        let sm: { path: string; exists: boolean } | undefined;
        if (emulatorOption.stateDir) {
          const stateRoot = emulatorOption.coreFolderName ? dirname(emulatorOption.stateDir) : emulatorOption.stateDir;
          const stateFolder = join(stateRoot, gameFolderName);
          const hasStateFiles = !!findLatestFileInDir(stateFolder);
          sm = { path: stateFolder, exists: hasStateFiles };
        }

        const launchCommand = emulatorOption.corePath
          ? `${emulatorOption.execPath} -L "${emulatorOption.corePath}" "${romPath}"`
          : `${emulatorOption.execPath} "${romPath}"`;
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
      statesDir: emulatorOption.stateDir ?? "", coresDir: "", romDirs: emulatorOption.romDirs }],
    romDirs,
    roms,
  };
}
