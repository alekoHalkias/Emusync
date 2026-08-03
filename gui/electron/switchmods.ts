// Communal Switch mod pool IPC (#444): local folder listing needs main-process
// filesystem access (mirrors gamefolder.ts); the actual push/pull/tar sync
// logic stays in Python (cli/run_switch.py's _sync_switch_mods, cli/mod.py) —
// "sync now" just shells out to the CLI rather than duplicating that logic here.
import { ipcMain, shell } from "electron";
import { existsSync, readdirSync } from "fs";
import { join } from "path";
import { homedir } from "os";
import { spawn } from "child_process";
import { SCRIPT, PYTHON } from "./runtime";

// Mirrors cli/run_switch.py's _SWITCH_LOAD_ROOTS.
function loadRoots(): string[] {
  return [
    join(homedir(), ".local/share/eden/load"),
    join(homedir(), "Emulation/storage/eden/load"),
  ];
}

export function registerSwitchModsIpc(): void {
  ipcMain.handle("switchMods:listLocal", (_event, titleId: string): string[] => {
    const names = new Set<string>();
    for (const root of loadRoots()) {
      const titleDir = join(root, titleId);
      if (!existsSync(titleDir)) continue;
      try {
        for (const entry of readdirSync(titleDir, { withFileTypes: true })) {
          if (entry.isDirectory()) names.add(entry.name);
        }
      } catch {
        // unreadable — skip
      }
    }
    return [...names].sort();
  });

  ipcMain.handle("switchMods:reveal", async (_event, titleId: string): Promise<{ ok: boolean; error?: string }> => {
    for (const root of loadRoots()) {
      const titleDir = join(root, titleId);
      if (existsSync(titleDir)) {
        const err = await shell.openPath(titleDir);
        return err ? { ok: false, error: err } : { ok: true };
      }
    }
    return { ok: false, error: "No local mods folder found for this game yet" };
  });

  ipcMain.handle("switchMods:sync", (_event, slug: string): Promise<{ ok: boolean; output: string }> => {
    return new Promise((resolve) => {
      const proc = spawn(PYTHON, [SCRIPT, "mod", "sync", slug]);
      let output = "";
      proc.stdout.on("data", (d) => (output += d.toString()));
      proc.stderr.on("data", (d) => (output += d.toString()));
      proc.on("close", (code) => resolve({ ok: code === 0, output: output.trim() }));
      proc.on("error", (e: Error) => resolve({ ok: false, output: e.message }));
    });
  });
}
