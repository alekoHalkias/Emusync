// Emulator dropdown for game and console settings (#753): emulators detected on
// this device for the console, an optional "Custom command", and "More..." last,
// which opens the import wizard's install panel inline.
import React, { useCallback, useEffect, useState } from "react";
import type { CoreInstallTargets } from "../../emusync";
import type { EmulatorOption } from "../console-import/types";
import { InstallOptions, SuggestionLinks } from "../console-import/EmulatorStep";

export type PickerOption = EmulatorOption & { stateDir?: string; launchArgs?: string[]; systemDir?: string };
export const CUSTOM = "__custom";
const MORE = "__more";
const NO_INSTALL: CoreInstallTargets = { retroarch: [], cores: [], standalones: [] };

export type EmulatorOptions = {
  options: PickerOption[];
  install: CoreInstallTargets;
  suggestions: string[];
  loaded: boolean;
  installCore: (coresDir: string, lib: string) => Promise<string | null>;
  installFlatpak: (flatpakId: string) => Promise<string | null>;
};

/** Detected emulators for a console; installs re-detect so the list updates in place. */
export function useEmulatorOptions(consoleKey: string): EmulatorOptions {
  const [options, setOptions] = useState<PickerOption[]>([]);
  const [install, setInstall] = useState<CoreInstallTargets>(NO_INSTALL);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [loaded, setLoaded] = useState(false);

  const detect = useCallback(async () => {
    if (!consoleKey) return;
    const det = await window.emusync.emulator.detect(consoleKey).catch(() => null);
    setOptions(det?.options ?? []);
    setInstall(det?.install ?? NO_INSTALL);
    setSuggestions(Array.isArray(det?.suggestions) ? det!.suggestions : []);
    setLoaded(true);
  }, [consoleKey]);

  useEffect(() => { detect(); }, [detect]);

  const after = async (res: { ok: boolean; error?: string }): Promise<string | null> => {
    if (!res.ok) return res.error ?? "Install failed";
    await detect();
    return null;
  };
  return {
    options, install, suggestions, loaded,
    installCore: (coresDir, lib) => window.emusync.emulator.installCore(consoleKey, coresDir, lib).then(after),
    installFlatpak: (id) => window.emusync.emulator.installFlatpak(consoleKey, id).then(after),
  };
}

/** The detected option a stored launch command was built from, else null (Custom).
 *  A RetroArch option needs both its binary and its core in the command. */
export function matchOption(cmd: string, options: PickerOption[]): PickerOption | null {
  if (!cmd) return null;
  return options.find(o => o.corePath && o.execPath && cmd.includes(o.execPath) && cmd.includes(o.corePath))
    ?? options.find(o => !o.corePath && o.execPath && cmd.includes(o.execPath))
    ?? null;
}

type Props = {
  id: string;
  emu: EmulatorOptions;
  value: string;                      // option id, CUSTOM, or "" (not set)
  onChange: (value: string) => void;
  allowCustom?: boolean;
  disabled?: boolean;
};

export function EmulatorPicker({ id, emu, value, onChange, allowCustom = true, disabled }: Props): React.ReactElement {
  const [showMore, setShowMore] = useState(false);
  const noInstall = !emu.install.cores.length && !(emu.install.standalones ?? []).length;
  return (
    <>
      <select id={id} value={value} disabled={disabled || !emu.loaded} onChange={(e) => {
        if (e.target.value === MORE) { setShowMore(true); return; }
        onChange(e.target.value);
      }}>
        {!emu.loaded && <option value={value}>Detecting emulators...</option>}
        {emu.loaded && (value === "" || !emu.options.length) && <option value="">{emu.options.length ? "Not set" : "No emulator found"}</option>}
        {emu.options.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
        {allowCustom && <option value={CUSTOM}>Custom command</option>}
        <option value={MORE}>More...</option>
      </select>
      {showMore && (
        <div className="card" style={{ marginTop: 8, padding: 12 }}>
          <InstallOptions install={emu.install} installCore={emu.installCore} installFlatpak={emu.installFlatpak} />
          {noInstall && <p style={{ fontSize: 12, color: "var(--text-muted)" }}>Download an emulator for this console:</p>}
          <SuggestionLinks suggestions={emu.suggestions} />
          <div className="modal-actions">
            <button className="btn btn-ghost" onClick={() => setShowMore(false)}>Close</button>
          </div>
        </div>
      )}
    </>
  );
}
