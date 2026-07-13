// Per-ROM path resolution for the import wizard's _runImport loop: renames the
// ROM (+ save/state) to the cleaned title and, for a network import, uploads a
// local-only ROM to the share or derives its portable rel-path (issue #255/#270).
import { relPathUnder } from "./helpers";
import type { RomEntry } from "./types";

// IPC bridge (typing deferred to the typed-bridge work in #228).
const emusync = window.emusync;

export interface ResolvedRomPaths {
  romPath: string;
  savePath: string;
  statePath: string;
  launchCmd: string;
  romRelPath: string;
  netRoot: string;
  localCopyPath: string;
  romSha: string;
}

export async function resolveImportPaths(
  rom: RomEntry,
  opts: {
    romSource: "local" | "network";
    localRomRoot: string;
    scanRoots: string[];
    scanRoot: string;
    safeBase: string;
    sharedLayout: boolean;       // save is a shared console card — never rename it
    sharedStateLayout: boolean;  // states are shared too (PS2 only, #402)
  },
): Promise<ResolvedRomPaths> {
  const { romSource, localRomRoot, scanRoots, scanRoot, safeBase, sharedLayout, sharedStateLayout } = opts;

  let romPath = rom.romPath;
  let savePath = rom.savePath;
  let statePath = rom.statePath ?? "";
  let launchCmd = rom.launchCommand;

  // Network ROMs: never reorganise the share — store the master path as-is
  // plus a portable rel-path. local_rom_path is EMPTY for a network-only
  // ROM, but holds the existing local file when the ROM was also found on
  // local disk (presence "both") or was uploaded from local disk
  // (presence "local") — in both cases the game is treated as already
  // localized. Local-source ROMs: organise into a per-game subfolder.
  let romRelPath = "";
  let netRoot = "";
  let localCopyPath = "";
  let romSha = "";
  if (romSource === "network") {
    const lRoot = (localRomRoot || "").replace(/\/$/, "");
    const networkRoots = scanRoots.filter(r => r !== lRoot);
    if (rom.presence === "local") {
      // Found only on local disk → rename to the cleaned title, then copy it
      // UP to the share so the share becomes the master, keeping the local
      // file as the localized copy.
      let localPath = rom.localRomPath ?? romPath;
      netRoot = networkRoots[0] ?? "";
      if (!netRoot) throw new Error("no network folder configured to upload to");
      const renamed = await emusync.files.renameGameFiles({
        romPath: localPath, savePath: sharedLayout ? "" : savePath,
        stateFolder: sharedStateLayout ? "" : statePath,
        newBase: safeBase, reorganize: false,
      });
      if (renamed.ok) {
        launchCmd = launchCmd.replaceAll(localPath, renamed.newRomPath);
        localPath = renamed.newRomPath;
        if (!sharedLayout) savePath = renamed.newSavePath;
        if (!sharedStateLayout) statePath = renamed.newStateFolder;
      }
      const rel = relPathUnder(localPath, [localRomRoot]);
      const masterPath = `${netRoot}/${rel}`;
      const up = await emusync.rom.uploadMaster(localPath, masterPath);
      if (!up.ok) throw new Error(up.error ?? "upload to share failed");
      launchCmd     = launchCmd.replaceAll(localPath, masterPath);
      romPath       = masterPath;       // master is now the canonical ROM
      romRelPath    = rel;
      localCopyPath = localPath;        // existing local file = localized copy
      romSha        = up.sha256 ?? "";
    } else {
      // network-only or both: romPath is the share master as scanned. Rename
      // the master (and the local copy, if any) + save/state to the title.
      netRoot = networkRoots.find(r => romPath === r || romPath.startsWith(r + "/")) ?? scanRoot;
      const renamed = await emusync.files.renameGameFiles({
        romPath, savePath: sharedLayout ? "" : savePath,
        stateFolder: sharedStateLayout ? "" : statePath,
        newBase: safeBase, reorganize: false,
        secondaryRomPath: rom.presence === "both" ? (rom.localRomPath ?? undefined) : undefined,
      });
      if (renamed.ok) {
        launchCmd = launchCmd.replaceAll(romPath, renamed.newRomPath);
        romPath   = renamed.newRomPath;
        if (!sharedLayout) savePath = renamed.newSavePath;
        if (!sharedStateLayout) statePath = renamed.newStateFolder;
        if (rom.presence === "both") localCopyPath = renamed.newSecondaryRomPath ?? (rom.localRomPath ?? "");
      }
      romRelPath = relPathUnder(romPath, networkRoots);
    }
  } else {
    // Local import: rename the ROM (+ save/state) to the cleaned title, and
    // nest a flat ROM into a per-game subfolder. Safe no-op when unchanged.
    const romParent = romPath.includes("/") ? romPath.substring(0, romPath.lastIndexOf("/")) : "";
    const flat = !!scanRoot && romParent === scanRoot;
    const renamed = await emusync.files.renameGameFiles({
      romPath, savePath: sharedLayout ? "" : savePath,
      stateFolder: sharedStateLayout ? "" : statePath,
      newBase: safeBase, reorganize: flat,
    });
    if (renamed.ok) {
      launchCmd  = launchCmd.replaceAll(romPath, renamed.newRomPath);
      romPath    = renamed.newRomPath;
      if (!sharedLayout) savePath = renamed.newSavePath;
      if (!sharedStateLayout) statePath = renamed.newStateFolder;
    }
  }

  return { romPath, savePath, statePath, launchCmd, romRelPath, netRoot, localCopyPath, romSha };
}
