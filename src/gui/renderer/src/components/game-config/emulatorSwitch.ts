// Emulator switch planning shared by game and console settings (#753). Paths
// come from scan.ts via `emulator:resolveGame`; this module only applies the
// keep-rules and, for a console-wide switch, writes each game's config.
import { getGameDevice, listMyGameDevices, setGameDevice, type GameDeviceConfig } from "../../api";
import { matchOption, type PickerOption } from "./EmulatorPicker";

export type SwitchPlan = {
  launchCommand: string;
  savePath: string;
  statePath: string;
  fromSave: string;     // current paths, the move sources
  fromState: string;
};

type PlanInput = {
  consoleKey: string;
  option: PickerOption;
  romPath: string;
  scanRoot?: string;
  savePath: string;
  statePath: string;
  // Per-game switch on a shared-layout console keeps the card / PS2 sstates;
  // only a console-level switch moves them.
  keepSave: boolean;
  keepState: boolean;
};

export async function planSwitch(p: PlanInput): Promise<SwitchPlan> {
  const r = await window.emusync.emulator.resolveGame({
    consoleKey: p.consoleKey, option: p.option, romPath: p.romPath, scanRoot: p.scanRoot,
  });
  return {
    launchCommand: r.launchCommand,
    // Blank resolved save = learned after first play (Switch/PS3): keep the current one.
    savePath: p.keepSave || !r.savePath ? p.savePath : r.savePath,
    statePath: p.keepState ? p.statePath : r.statePath,
    fromSave: p.savePath,
    fromState: p.statePath,
  };
}

export const pathsChanged = (s: SwitchPlan): boolean => s.savePath !== s.fromSave || s.statePath !== s.fromState;

const romInUse = (cfg: GameDeviceConfig): string =>
  cfg.rom_source === "network" && cfg.local_rom_path ? cfg.local_rom_path : cfg.rom_path;

export type ConsoleSwitchItem = { slug: string; name: string; cfg: GameDeviceConfig; plan: SwitchPlan };

/** This device's games on the console, planned for `option`; Custom-command games are left out. */
export async function previewConsoleSwitch(
  abbr: string, consoleKey: string, option: PickerOption, options: PickerOption[],
): Promise<{ items: ConsoleSwitchItem[]; customCount: number }> {
  const mine = (await listMyGameDevices()).filter(g => (g.console ?? "").toLowerCase() === abbr.toLowerCase());
  const items: ConsoleSwitchItem[] = [];
  let customCount = 0;
  for (const g of mine) {
    const cfg = await getGameDevice(g.slug).catch(() => null);
    if (!cfg?.rom_path) continue;
    if (!matchOption(cfg.launch_command, options)) { customCount++; continue; }
    const plan = await planSwitch({
      consoleKey, option, romPath: romInUse(cfg), scanRoot: cfg.rom_folder_path,
      savePath: cfg.save_path, statePath: cfg.state_path ?? "", keepSave: false, keepState: false,
    });
    items.push({ slug: g.slug, name: g.name, cfg, plan });
  }
  return { items, customCount };
}

/** Optionally move each game's saves, then store the new command and paths.
 *  Shared cards/sstates need no dedupe: after the first game moves them the
 *  source is gone and later moves are no-ops. */
export async function applyConsoleSwitch(items: ConsoleSwitchItem[], move: boolean): Promise<{
  updated: number; moved: number; skipped: string[]; errors: string[];
}> {
  const out = { updated: 0, moved: 0, skipped: [] as string[], errors: [] as string[] };
  for (const { slug, name, cfg, plan } of items) {
    if (move && pathsChanged(plan)) {
      const res = await window.emusync.emulator.moveSaves({
        fromSave: plan.fromSave, toSave: plan.savePath, fromState: plan.fromState, toState: plan.statePath,
      });
      out.moved += res.moved.length;
      out.skipped.push(...res.skipped);
      // A failed move leaves this game on its old emulator rather than pointing at empty paths.
      if (!res.ok) { out.errors.push(`${name}: ${res.error ?? "move failed"}`); continue; }
    }
    try {
      await setGameDevice(slug, { ...cfg, launch_command: plan.launchCommand, save_path: plan.savePath, state_path: plan.statePath });
      out.updated++;
    } catch {
      out.errors.push(`${name}: couldn't save config`);
    }
  }
  return out;
}
