// IPC for the console-based emulator import wizard.
import { ipcMain } from "electron";
import { homedir } from "os";
import { dirname } from "path";
import { rt } from "../runtime";
import { loadConsoleDefinitionsIfNeeded } from "./console-defs";
import { coreInstallTargets, detectEmulatorsForConsole, type CoreInstallTargets } from "./detect";
import { findRomByNameSize, resolveRomEntry, runEmulatorScan } from "./scan";
import { moveSaves, type MoveSavesParams, type MoveSavesResult } from "./moveSaves";
import { installCore } from "./installCore";
import { installFlatpak } from "./installFlatpak";
import { scanLibraryFolders, type LibraryFolderMatch } from "./library";
import type { DetectedEmulatorOption, EmulatorScanResult } from "./types";

export function registerEmulatorIpc(): void {
  ipcMain.handle("emulator:consoles", async () => {
    await loadConsoleDefinitionsIfNeeded();
    return Object.values(rt.cachedConsoleDefs || {}).map(c => ({
      key: c.key, label: c.label, abbr: c.abbr,
      sharedMemcard: !!c.sharedMemcard, sharedState: !!c.sharedState,
    }));
  });

  ipcMain.handle("emulator:detect", async (_event, consoleKey: string): Promise<{
    options: DetectedEmulatorOption[];
    suggestions: string[];
    install: CoreInstallTargets;
  }> => {
    await loadConsoleDefinitionsIfNeeded();
    const consoleDef = rt.cachedConsoleDefs?.[consoleKey];
    return {
      options: detectEmulatorsForConsole(homedir(), consoleKey),
      suggestions: consoleDef?.suggestions ?? [],
      install: coreInstallTargets(homedir(), consoleKey),
    };
  });

  ipcMain.handle("emulator:installCore", async (_event, consoleKey: string, coresDir: string, lib: string) => {
    await loadConsoleDefinitionsIfNeeded();
    return installCore(homedir(), consoleKey, coresDir, lib);
  });

  ipcMain.handle("emulator:installFlatpak", async (_event, consoleKey: string, flatpakId: string) => {
    await loadConsoleDefinitionsIfNeeded();
    return installFlatpak(homedir(), consoleKey, flatpakId);
  });

  ipcMain.handle("emulator:scan", async (_event, params: {
    consoleKey: string;
    emulatorOption: DetectedEmulatorOption;
    extraPaths: string[];
  }): Promise<EmulatorScanResult> => {
    await loadConsoleDefinitionsIfNeeded();
    return runEmulatorScan(params);
  });

  // One ROM under one detected emulator: launch command + save/state paths (#753).
  ipcMain.handle("emulator:resolveGame", async (_event, params: {
    consoleKey: string;
    option: DetectedEmulatorOption;
    romPath: string;
    scanRoot?: string;
  }) => {
    await loadConsoleDefinitionsIfNeeded();
    const e = resolveRomEntry(params.consoleKey, params.option, params.romPath, params.scanRoot || dirname(params.romPath));
    return { savePath: e.savePath, saveExists: e.saveExists, statePath: e.statePath ?? "", stateExists: !!e.stateExists, launchCommand: e.launchCommand };
  });

  // Move save/state files to a new emulator's paths; never overwrites (#753).
  ipcMain.handle("emulator:moveSaves", (_event, params: MoveSavesParams): MoveSavesResult => moveSaves(params));

  // Same ROM by filename + size under a set of folders (#731); null when ambiguous.
  ipcMain.handle("rom:findByNameSize", (_event, roots: string[], filename: string, size: number): string | null =>
    findRomByNameSize(roots, filename, size));

  // Bulk-library import (#462): non-recursive scan of a library root's
  // immediate subfolders, each matched against known console names.
  ipcMain.handle("emulator:scanLibrary", async (_event, libraryRoot: string): Promise<LibraryFolderMatch[]> => {
    await loadConsoleDefinitionsIfNeeded();
    return scanLibraryFolders(libraryRoot);
  });
}
