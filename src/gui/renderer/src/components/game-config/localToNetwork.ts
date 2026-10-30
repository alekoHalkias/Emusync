import { getGameDevice, setGameDevice } from "../../api";
import { relPathUnder } from "../console-import/helpers";

export const norm = (p: string): string => p.replace(/\\/g, "/").replace(/\/+$/, "");

export type UploadResult =
  | { ok: true; master: string; launch: string; rel: string; sha: string; skipped: boolean }
  | { ok: false; error: string };

/** Upload a local-source ROM to the console's network folder and flip the game to
 *  network-sourced, keeping the local file as the local copy (#624, mirrors the
 *  import wizard's presence="local" branch). Never overwrites an existing master. */
export async function uploadLocalRom(slug: string, romPath: string, folder: string, netFolder: string): Promise<UploadResult> {
  const rel = relPathUnder(norm(romPath), folder ? [norm(folder)] : []);
  const master = `${norm(netFolder)}/${rel}`;
  const up = await window.emusync.rom.uploadMaster(romPath, master);
  if (!up.ok) return { ok: false, error: up.error ?? "Upload failed." };
  const gd = await getGameDevice(slug);
  const launch = gd.launch_command ? gd.launch_command.split(romPath).join(master) : gd.launch_command;
  const sha = up.sha256 ?? "";
  await setGameDevice(slug, {
    ...gd, rom_source: "network", rom_path: master, local_rom_path: romPath,
    rom_rel_path: rel, rom_sha256: sha, launch_command: launch,
  });
  return { ok: true, master, launch: launch ?? "", rel, sha, skipped: !!up.skipped };
}
