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
