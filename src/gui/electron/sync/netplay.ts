// Cross-device network-drive play: link a game another device has on a network
// share to THIS device's own mount of that share (issues #270, #729).
import { ipcMain } from "electron";
import { existsSync } from "fs";
import { join, dirname } from "path";
import { loadServerCfg } from "../config-store";

type ServerCfg = ReturnType<typeof loadServerCfg>;

/** Portable bits of another device's network config (GET /games/{slug}/network-source). */
type NetworkSource = {
  console: string; rom_path: string; rom_rel_path: string;
  launch_command: string; save_path: string; state_path: string;
};

/** Join `mountRoot` + `src.rom_rel_path`, verify the ROM exists, rebase the
 * launch command and save/state paths onto this device, and save the config.
 * Save/state paths come from this device's console folders when configured;
 * run.py's post-launch auto-detection refines them on first play. */
async function linkNetworkGame(
  cfg: ServerCfg, slug: string, src: NetworkSource, mountRoot: string,
): Promise<{ ok: boolean; romPath?: string; error?: string }> {
  const { host, port, authHeaders } = cfg;
  const rel = src.rom_rel_path;
  // Reject traversal / absolute / drive-qualified rel-paths before joining.
  const segs = rel.replace(/\\/g, "/").split("/").filter(Boolean);
  if (!rel || rel.includes(":") || segs.some(s => s === "..")) {
    return { ok: false, error: `Unsafe ROM path from source device: ${rel}` };
  }
  const romPath = join(mountRoot, ...segs);
  if (!existsSync(romPath)) {
    return { ok: false, error: `ROM not found at ${romPath}. Check that the share is mounted and the root is correct.` };
  }

  // Reuse the source's per-game tail (GameName/GameName.srm and GameName/).
  const folders = await consoleSaveStateFolders(cfg, src.console);
  const saveTail = tailSegments(src.save_path, 2);
  const stateTail = tailSegments(src.state_path, 1);
  const savePath = folders.saveFolder && saveTail.length
    ? join(folders.saveFolder, ...saveTail)
    : src.save_path;
  const statePath = src.state_path
    ? (folders.stateFolder && stateTail.length ? join(folders.stateFolder, ...stateTail) : src.state_path)
    : "";

  const launchCommand = src.rom_path
    ? src.launch_command.split(src.rom_path).join(romPath)
    : src.launch_command;

  const updated = {
    rom_path: romPath,
    save_path: savePath,
    state_path: statePath,
    launch_command: launchCommand,
    rom_folder_path: dirname(romPath),
    rom_source: "network",
    rom_rel_path: rel,
    local_rom_path: "",
    device_network_folder: mountRoot,
  };
  const putRes = await fetch(`http://${host}:${port}/games/${slug}/device`, {
    method: "PUT",
    headers: { ...authHeaders, "Content-Type": "application/json" },
    body: JSON.stringify(updated),
    signal: AbortSignal.timeout(5000),
  });
  if (!putRes.ok) return { ok: false, error: "Verified the ROM, but failed to save the config" };
  return { ok: true, romPath };
}

export function registerNetPlayIpc(): void {
  // Play-time setup for one game against a chosen mount root (issue #270).
  ipcMain.handle(
    "rom:setupNetworkPlay",
    async (_event, slug: string, mountRoot: string): Promise<{ ok: boolean; romPath?: string; error?: string }> => {
      try {
        if (!mountRoot) return { ok: false, error: "No mount root selected" };
        const cfg = loadServerCfg();
        const srcRes = await fetch(`http://${cfg.host}:${cfg.port}/games/${slug}/network-source`, { headers: cfg.authHeaders, signal: AbortSignal.timeout(5000) });
        if (!srcRes.ok) return { ok: false, error: "No network-drive config found for this game on any device" };
        return await linkNetworkGame(cfg, slug, await srcRes.json() as NetworkSource, mountRoot);
      } catch (e: any) {
        return { ok: false, error: e.message || "Network play setup failed" };
      }
    }
  );

  // Link every network game whose share ID matches one of this device's
  // consoles (issue #729). The server picks the candidates; a ROM missing from
  // this device's mount is skipped silently and stays unlinked.
  ipcMain.handle("rom:autoLinkNetworkGames", async (): Promise<{ ok: boolean; linked: number }> => {
    try {
      const cfg = loadServerCfg();
      const res = await fetch(`http://${cfg.host}:${cfg.port}/games/network-link-candidates`, { headers: cfg.authHeaders, signal: AbortSignal.timeout(5000) });
      if (!res.ok) return { ok: false, linked: 0 };
      const candidates = await res.json() as Array<NetworkSource & { slug: string; mount_root: string }>;
      let linked = 0;
      for (const c of candidates) {
        try {
          if ((await linkNetworkGame(cfg, c.slug, c, c.mount_root)).ok) linked++;
        } catch { /* skip this game */ }
      }
      return { ok: true, linked };
    } catch {
      return { ok: false, linked: 0 };
    }
  });
}

/** Last `n` path segments of `p` (splitting on / or \), for rebasing a path. */
function tailSegments(p: string, n: number): string[] {
  if (!p) return [];
  const segs = p.replace(/\\/g, "/").split("/").filter(Boolean);
  return segs.slice(Math.max(0, segs.length - n));
}

// This device's configured save/state folders for a console (set during import),
// used to place a cross-device network game's saves/states locally (issue #270).
async function consoleSaveStateFolders(
  { host, port, authHeaders }: ServerCfg, consoleName: string,
): Promise<{ saveFolder: string; stateFolder: string }> {
  try {
    const whoamiRes = await fetch(`http://${host}:${port}/whoami`, { headers: authHeaders, signal: AbortSignal.timeout(5000) });
    if (!whoamiRes.ok) return { saveFolder: "", stateFolder: "" };
    const { device_id } = await whoamiRes.json() as { device_id: string };
    const consolesRes = await fetch(`http://${host}:${port}/devices/${device_id}/consoles`, { headers: authHeaders, signal: AbortSignal.timeout(5000) });
    if (!consolesRes.ok) return { saveFolder: "", stateFolder: "" };
    const consoles = await consolesRes.json() as Array<{ console_name: string; device_save_folder?: string; device_state_folder?: string }>;
    const matches = consoles.filter(c => c.console_name === consoleName);
    return {
      saveFolder: matches.find(c => c.device_save_folder)?.device_save_folder || "",
      stateFolder: matches.find(c => c.device_state_folder)?.device_state_folder || "",
    };
  } catch {
    return { saveFolder: "", stateFolder: "" };
  }
}
