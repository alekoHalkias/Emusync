// Emulator picker state for one game's settings form (#753). The switch only
// edits the form; the save move is queued and run by the form's Save.
import { useEffect, useRef, useState } from "react";
import { CUSTOM, matchOption, useEmulatorOptions, type PickerOption } from "./EmulatorPicker";
import { pathsChanged, planSwitch, type SwitchPlan } from "./emulatorSwitch";

type Move = { fromSave: string; toSave: string; fromState: string; toState: string };

type Args = {
  gameConsole: string;          // stored abbr, e.g. "GBA"
  ready: boolean;               // gameConsole has been loaded (blank then means no console)
  launchCommand: string;
  romPath: string;              // ROM in use (local copy for network games)
  scanRoot?: string;
  savePath: string;
  statePath: string;
  sharedLayout: boolean;
  sharedStateLayout: boolean;
  apply: (plan: SwitchPlan) => void;
};

export function useGameEmulator(a: Args) {
  const [consoleKey, setConsoleKey] = useState("");
  // Until resolved, a blank consoleKey means "still loading", not "no console",
  // so the form shows the picker's loading state instead of the raw input.
  const [resolved, setResolved] = useState(false);
  useEffect(() => {
    if (!a.ready) return;
    if (!a.gameConsole) { setConsoleKey(""); setResolved(true); return; }
    window.emusync.emulator.consoles().then(defs => {
      const def = defs.find(d => (d.abbr ?? "").toLowerCase() === a.gameConsole.toLowerCase());
      setConsoleKey(def?.key ?? "");
    }).catch(() => {}).finally(() => setResolved(true));
  }, [a.ready, a.gameConsole]);

  const emu = useEmulatorOptions(consoleKey);
  const [value, setValue] = useState("");
  const inited = useRef(false);
  useEffect(() => {
    if (inited.current || !emu.loaded || !a.launchCommand) return;
    inited.current = true;
    setValue(matchOption(a.launchCommand, emu.options)?.id ?? CUSTOM);
  }, [emu.loaded, emu.options, a.launchCommand]);

  const [pending, setPending] = useState<{ option: PickerOption; plan: SwitchPlan; fromLabel: string } | null>(null);
  const [error, setError] = useState("");
  const move = useRef<Move | null>(null);

  async function pick(v: string): Promise<void> {
    setError("");
    if (v === CUSTOM || v === "") { setValue(v); return; }
    const option = emu.options.find(o => o.id === v);
    if (!option) return;
    if (!a.romPath) { setError("Choose the ROM file first."); return; }
    try {
      const plan = await planSwitch({
        consoleKey, option, romPath: a.romPath, scanRoot: a.scanRoot, savePath: a.savePath, statePath: a.statePath,
        keepSave: a.sharedLayout, keepState: a.sharedStateLayout,
      });
      const fromLabel = emu.options.find(o => o.id === value)?.label ?? "";
      setPending({ option, plan, fromLabel });
    } catch {
      setError("Couldn't work out paths for that emulator.");
    }
  }

  function confirm(doMove: boolean): void {
    if (!pending) return;
    const { plan, option } = pending;
    // A second switch before Save keeps moving from the files' real location.
    const prev = move.current;
    move.current = doMove && pathsChanged(plan)
      ? { fromSave: prev?.fromSave ?? plan.fromSave, toSave: plan.savePath, fromState: prev?.fromState ?? plan.fromState, toState: plan.statePath }
      : null;
    a.apply(plan);
    setValue(option.id);
    setPending(null);
  }

  /** The queued move, cleared once taken (Save runs it before storing the config). */
  function takeMove(): Move | null {
    const m = move.current;
    move.current = null;
    return m;
  }

  const modal = pending && {
    fromLabel: pending.fromLabel,
    toLabel: pending.option.label,
    savePath: pending.plan.savePath !== pending.plan.fromSave ? pending.plan.savePath : undefined,
    statePath: pending.plan.statePath !== pending.plan.fromState ? pending.plan.statePath : undefined,
    onCancel: () => setPending(null),
    onConfirm: confirm,
  };

  return { consoleKey, resolving: !resolved, emu, value, pick, error, modal, takeMove, restoreMove: (m: Move) => { move.current = m; } };
}
