// IPC for the console-based emulator import wizard.
import { ipcMain } from "electron";
import { homedir } from "os";
import { rt } from "../runtime";
import { loadConsoleDefinitionsIfNeeded } from "./console-defs";
import { detectEmulatorsForConsole } from "./detect";
import { runEmulatorScan } from "./scan";
import type { DetectedEmulatorOption, EmulatorScanResult } from "./types";

export function registerEmulatorIpc(): void {
  ipcMain.handle("emulator:consoles", async () => {
    await loadConsoleDefinitionsIfNeeded();
    return Object.values(rt.cachedConsoleDefs || {}).map(c => ({ key: c.key, label: c.label, abbr: c.abbr }));
  });

  ipcMain.handle("emulator:detect", async (_event, consoleKey: string): Promise<{
    options: DetectedEmulatorOption[];
    suggestions: string[];
  }> => {
    await loadConsoleDefinitionsIfNeeded();
    const consoleDef = rt.cachedConsoleDefs?.[consoleKey];
    return {
      options: detectEmulatorsForConsole(homedir(), consoleKey),
      suggestions: consoleDef?.suggestions ?? [],
    };
  });

  ipcMain.handle("emulator:scan", async (_event, params: {
    consoleKey: string;
    emulatorOption: DetectedEmulatorOption;
    extraPaths: string[];
  }): Promise<EmulatorScanResult> => {
    await loadConsoleDefinitionsIfNeeded();
    return runEmulatorScan(params);
  });
}
