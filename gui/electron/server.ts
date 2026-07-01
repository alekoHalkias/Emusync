// Python server + sync-daemon process lifecycle, and the server:* / daemon:* IPC.
import { ipcMain } from "electron";
import { spawn } from "child_process";
import { existsSync, readFileSync, writeFileSync, unlinkSync } from "fs";
import { join } from "path";
import { homedir, networkInterfaces } from "os";
import { parse as parseTOML, stringify as stringifyTOML } from "smol-toml";
import { CONFIG_PATH, SCRIPT, PYTHON, rt } from "./runtime";

// ── sync daemon ─────────────────────────────────────────────────────────────

export function startSyncDaemon(): void {
  if (rt.syncDaemonProcess) return;

  // Only start for client devices (server devices run it embedded in the server process)
  if (existsSync(CONFIG_PATH)) {
    try {
      const cfg = parseTOML(readFileSync(CONFIG_PATH, "utf-8")) as Record<string, unknown>;
      if (cfg.is_server) return;
    } catch { return; }
  } else {
    return; // No config yet (fresh install showing setup screen)
  }

  try {
    const proc = spawn(PYTHON, [SCRIPT, "sync-daemon"], {
      stdio: "ignore",
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
    });
    rt.syncDaemonProcess = proc;

    proc.on("exit", () => {
      rt.syncDaemonProcess = null;
      // Restart after 10 s — server may have been temporarily unreachable
      rt.syncDaemonRestartTimer = setTimeout(() => {
        rt.syncDaemonRestartTimer = null;
        startSyncDaemon();
      }, 10_000);
    });

    proc.on("error", (err) => {
      console.error("Sync daemon error:", err);
      rt.syncDaemonProcess = null;
    });
  } catch (err) {
    console.error("Failed to start sync daemon:", err);
  }
}

export function stopSyncDaemon(): void {
  if (rt.syncDaemonRestartTimer) {
    clearTimeout(rt.syncDaemonRestartTimer);
    rt.syncDaemonRestartTimer = null;
  }
  if (rt.syncDaemonProcess) {
    rt.syncDaemonProcess.kill("SIGKILL");
    rt.syncDaemonProcess = null;
  }
}

// ── server process ──────────────────────────────────────────────────────────

export function startServerProcess(): Promise<{ ok: boolean }> {
  if (rt.serverProcess) return Promise.resolve({ ok: true });

  return new Promise<{ ok: boolean }>((resolve) => {
    let resolved = false;
    const proc = spawn(PYTHON, [SCRIPT, "server", "start"], {
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
    });
    rt.serverProcess = proc;

    // Resolve as soon as the server prints its startup line (before uvicorn binds)
    proc.stdout?.on("data", (chunk: Buffer) => {
      const line = chunk.toString();
      if (!resolved && line.includes("EmuSync server ready")) {
        resolved = true;
        rt.serverStartedByApp = true; // Server actually started; only kill it on close if we started it
        resolve({ ok: true });
      }
    });

    proc.on("error", (err) => {
      rt.serverProcess = null;
      if (!resolved) { resolved = true; resolve({ ok: false }); }
      console.error("Server process error:", err);
    });

    proc.on("exit", () => {
      rt.serverProcess = null;
    });

    // Fallback: resolve after 5 s if we never see the startup line
    setTimeout(() => {
      if (!resolved) { resolved = true; resolve({ ok: true }); }
    }, 5000);
  });
}

export function killServerByPid(): void {
  const pidFile = join(homedir(), ".emusync", ".server_pid");
  try {
    if (existsSync(pidFile)) {
      const pid = parseInt(readFileSync(pidFile, "utf-8").trim(), 10);
      if (pid) try { process.kill(pid, "SIGKILL"); } catch {}
      unlinkSync(pidFile);
    }
  } catch {}
  try { unlinkSync(join(homedir(), ".emusync", ".server_token")); } catch {}
}

export function killOrphanServers(): Promise<void> {
  return new Promise((resolve) => {
    // Kill any emusync server process not tracked by rt.serverProcess (orphans from previous sessions)
    const proc = spawn("pkill", ["-9", "-f", "emusync.py server start"], { stdio: "ignore" });
    proc.on("exit", resolve);
    proc.on("error", resolve);
    setTimeout(resolve, 1000);
  });
}

// ── IPC ─────────────────────────────────────────────────────────────────────

export function registerServerIpc(): void {
  ipcMain.handle("server:start", () => startServerProcess());

  ipcMain.handle("daemon:start", () => { startSyncDaemon(); });
  ipcMain.handle("daemon:stop",  () => { stopSyncDaemon(); });

  ipcMain.handle("server:stop", async () => {
    if (rt.serverProcess) {
      rt.serverProcess.kill("SIGKILL");
      rt.serverProcess = null;
    }
    killServerByPid();
    await killOrphanServers();
    rt.serverStartedByApp = false; // User explicitly stopped the server
    return true;
  });

  ipcMain.handle("server:discover", () => {
    return new Promise<Array<{ name: string; host: string; port: number }>>((resolve) => {
      const proc = spawn(PYTHON, [SCRIPT, "server", "discover-json"], {
        stdio: ["ignore", "pipe", "pipe"],
        env: { ...process.env, PYTHONUNBUFFERED: "1" },
      });
      let output = "";
      proc.stdout?.on("data", (chunk: Buffer) => { output += chunk.toString(); });
      proc.on("exit", () => { try { resolve(JSON.parse(output)); } catch { resolve([]); } });
      proc.on("error", () => resolve([]));
    });
  });

  ipcMain.handle("server:local-ip", (): string | null => {
    const nets = networkInterfaces();
    for (const name of Object.keys(nets)) {
      for (const iface of nets[name] ?? []) {
        if (iface.family === "IPv4" && !iface.internal) return iface.address;
      }
    }
    return null;
  });

  ipcMain.handle("server:change-pin", async (_event, pin: string | null) => {
    // Stop running server
    if (rt.serverProcess) {
      rt.serverProcess.kill("SIGKILL");
      rt.serverProcess = null;
    }
    killServerByPid();
    await killOrphanServers();

    // Save PIN to config
    const raw = existsSync(CONFIG_PATH) ? parseTOML(readFileSync(CONFIG_PATH, "utf-8")) as Record<string, unknown> : {};
    if (pin) {
      raw.server_pin = pin;
    } else {
      delete raw.server_pin;
    }
    writeFileSync(CONFIG_PATH, stringifyTOML(raw as any));

    return startServerProcess();
  });
}
