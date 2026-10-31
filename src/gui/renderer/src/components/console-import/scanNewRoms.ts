// Look for ROMs in a console's folders that no game on this device points at (#650).
// Same pipeline the wizard runs (scan, ignore filter, network/local merge, dedupe),
// without opening it, so Refresh can report a count first.
import { gamesOverview, getDeviceConsoles } from "../../api";
import { annotateRoms, classifyByRoot, dedupeAndLink } from "./helpers";
import { filterIgnored, loadIgnoredRoms } from "./ignoredRoms";

const emusync = window.emusync;

export type NewRomScan = {
  status: "ok" | "nofolders" | "noemulator" | "error";
  count: number;
  folders: string[];
  networkRoot: string;
  localRoot: string;
};

export async function scanNewRoms(consoleKey: string, deviceId: string): Promise<NewRomScan> {
  const none = { count: 0, folders: [] as string[], networkRoot: "", localRoot: "" };
  try {
    const defs = (await emusync.emulator.consoles().catch(() => [])) ?? [];
    const abbr = defs.find((d) => d.key === consoleKey)?.abbr ?? consoleKey;
    const row = (await getDeviceConsoles(deviceId)).find((c) => c.console_name.toLowerCase() === abbr.toLowerCase());
    const networkRoot = row?.device_network_folder ?? "";
    const localRoot = row?.device_local_folder ?? "";
    const folders = [...new Set([
      row?.device_game_folder ?? "", ...(row?.device_extra_folders ?? []), localRoot, networkRoot,
    ].filter(Boolean))];
    if (folders.length === 0) return { ...none, status: "nofolders" };

    const { options } = await emusync.emulator.detect(consoleKey);
    const emu = options.find((o: { label: string }) => o.label === row?.device_emulator) ?? options[0];
    if (!emu) return { ...none, status: "noemulator" };

    const [result, ignored, overview] = await Promise.all([
      emusync.emulator.scan(consoleKey, emu, folders),
      loadIgnoredRoms(consoleKey),
      gamesOverview(),
    ]);
    let roms = annotateRoms(filterIgnored(result.roms, new Set(ignored)), folders, result.romDirs ?? []);
    if (networkRoot) roms = classifyByRoot(roms, folders, localRoot);
    const configs = overview.filter((o) => o.rom_path).map((o) => ({ slug: o.slug, romPath: o.rom_path }));
    const { roms: fresh } = dedupeAndLink(roms, overview, configs);
    return { status: "ok", count: fresh.length, folders, networkRoot, localRoot };
  } catch {
    return { ...none, status: "error" };
  }
}
