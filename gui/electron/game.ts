// Game launch / stop / status IPC.
import { ipcMain } from "electron";
import { spawn } from "child_process";
import { existsSync, readFileSync } from "fs";
import { join, dirname } from "path";
import { homedir } from "os";
import { SCRIPT, PYTHON, rt } from "./runtime";

export function registerGameIpc(): void {
  ipcMain.handle("launcher:path", () => join(dirname(SCRIPT), "emusync"));

  ipcMain.handle("game:launch", (_event, slug: string) => {
    if (rt.gameProcess) return { ok: false };
    // The emulator command is derived server-side from the game config, so the
    // launcher only needs the slug.
    const proc = spawn(PYTHON, [SCRIPT, "run", slug], {
      stdio: "ignore",
      detached: true,
      env: { ...process.env, DISPLAY: process.env.DISPLAY || ":0", WAYLAND_DISPLAY: process.env.WAYLAND_DISPLAY || "wayland-0" },
    });
    rt.gameProcess = proc;
    proc.on("exit", () => {
      rt.gameProcess = null;
      rt.mainWindow?.webContents.send("game:exited");
    });
    proc.unref();
    return { ok: true };
  });

  ipcMain.handle("game:stop", () => {
    if (rt.gameProcess?.pid) {
      try { process.kill(-rt.gameProcess.pid, "SIGTERM"); } catch { rt.gameProcess.kill("SIGTERM"); }
      // Do NOT null rt.gameProcess here — let the exit event do it so game:isRunning()
      // stays true while the Python wrapper is still in its finally block (releasing
      // the lock), preventing the lock-polling race that shows "Playing on Steam".
    }
    return { ok: true };
  });

  ipcMain.handle("game:isRunning", () => rt.gameProcess !== null);

  ipcMain.handle("game:stop-external", () => {
    const gamePidFile = join(homedir(), ".emusync", ".game_pid");
    try {
      if (existsSync(gamePidFile)) {
        const lines = readFileSync(gamePidFile, "utf-8").trim().split("\n");
        const emusyncPid = parseInt(lines[0], 10);
        const childPid = lines[1] ? parseInt(lines[1], 10) : NaN;
        if (childPid) try { process.kill(childPid, "SIGKILL"); } catch {}
        if (emusyncPid) try { process.kill(emusyncPid, "SIGTERM"); } catch {}
      }
    } catch {}
    return { ok: true };
  });

  // Offline fallback game list (issue #383): when the server can't be reached at
  // all, the renderer has nothing to show from GET /games/overview. Build a list
  // from what cli/run.py cached on this device's last online launch of each game
  // (~/.emusync/game_cache/) so the user can still find and press Play.
  ipcMain.handle("game:offlineList", () => {
    const cacheDir = join(homedir(), ".emusync", "game_cache");
    const indexPath = join(cacheDir, "_offline_index.json");
    if (!existsSync(indexPath)) return [];
    let index: Record<string, { name?: string; console?: string }>;
    try {
      index = JSON.parse(readFileSync(indexPath, "utf-8"));
    } catch {
      return [];
    }
    const games: { slug: string; name: string; console: string; savePath?: string; statePath?: string }[] = [];
    for (const [slug, meta] of Object.entries(index)) {
      const gdPath = join(cacheDir, `${slug}.json`);
      if (!existsSync(gdPath)) continue;
      try {
        const gd = JSON.parse(readFileSync(gdPath, "utf-8"));
        games.push({
          slug,
          name: meta?.name || slug,
          console: meta?.console || "",
          savePath: gd.save_path || undefined,
          statePath: gd.state_path || undefined,
        });
      } catch { /* skip unreadable cache entry */ }
    }
    return games;
  });

  ipcMain.handle("game:hasPidFile", () => {
    const gamePidFile = join(homedir(), ".emusync", ".game_pid");
    if (!existsSync(gamePidFile)) return false;
    try {
      const pid = parseInt(readFileSync(gamePidFile, "utf-8").trim().split("\n")[0], 10);
      if (!pid) return false;
      try { process.kill(pid, 0); } catch { return false; }
      // Verify the process is actually emusync, not a recycled PID
      try {
        const cmdline = readFileSync(`/proc/${pid}/cmdline`, "utf-8");
        return cmdline.includes("emusync") || cmdline.includes("python");
      } catch { return true; } // non-Linux: trust the signal check
    } catch { return false; }
  });
}
