// Per-console settings editor for this device (#539, #629). One block per console:
// folders live on its primary `consoles` row, extra ROM folders in
// `device_extra_folders`; older one-row-per-folder entries are listed read-only.
import React, { useEffect, useState } from "react";
import { getDeviceConsoles, updateDeviceConsole, type DeviceConsole } from "../api";
import { useDevices } from "../DeviceContext";
import { usesSharedSaveLayout } from "./console-import/helpers";
import { EmulatorPicker, useEmulatorOptions } from "./game-config/EmulatorPicker";
import EmulatorSwitchModal from "./game-config/EmulatorSwitchModal";
import { applyConsoleSwitch, pathsChanged, previewConsoleSwitch, type ConsoleSwitchItem } from "./game-config/emulatorSwitch";
import IgnoredGamesPanel from "./IgnoredGamesPanel";
import Modal from "./Modal";

type Folders = Omit<DeviceConsole, "id" | "console_name">;
type TextKey = "device_game_folder" | "device_save_folder" | "device_state_folder" | "device_network_folder" | "device_local_folder";
const FIELDS: Array<{ key: TextKey; label: string }> = [
  { key: "device_game_folder", label: "ROM folder" },
  { key: "device_save_folder", label: "Save folder" },
  { key: "device_state_folder", label: "States folder" },
];

type Props = { consoleKey: string; onClose: () => void };

export default function ConsoleFoldersModal({ consoleKey, onClose }: Props): React.ReactElement {
  const { currentDeviceId } = useDevices();
  const [row, setRow] = useState<DeviceConsole | null | undefined>(undefined);
  const [origRom, setOrigRom] = useState("");
  const [legacy, setLegacy] = useState<string[]>([]);
  const emu = useEmulatorOptions(consoleKey);
  const [pending, setPending] = useState<{ id: string; items: ConsoleSwitchItem[]; customCount: number } | null>(null);
  const [switching, setSwitching] = useState(false);
  const [abbr, setAbbr] = useState("");
  const [loadFailed, setLoadFailed] = useState(false);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    if (!currentDeviceId) return;
    (async () => {
      const defs = (await window.emusync.emulator.consoles().catch(() => [])) ?? [];
      const a = defs.find((d) => d.key === consoleKey)?.abbr ?? consoleKey;
      setAbbr(a);
      const fetched = await getDeviceConsoles(currentDeviceId).catch(() => null);
      setLoadFailed(fetched === null);
      const all = (fetched ?? []).filter((c) => c.console_name.toLowerCase() === a.toLowerCase());
      const primary = all.find((c) => c.device_game_folder) ?? all[0] ?? null;
      setRow(primary);
      setOrigRom(primary?.device_game_folder ?? "");
      setLegacy(all.filter((c) => c !== primary && c.device_game_folder).map((c) => c.device_game_folder));
    })();
  }, [currentDeviceId, consoleKey]);

  const edit = (patch: Partial<DeviceConsole>): void => setRow((r) => r && { ...r, ...patch });

  async function browse(apply: (dir: string) => void): Promise<void> {
    const dir = await window.emusync.dialog.openFolder();
    if (dir) apply(dir);
  }

  const extras = row?.device_extra_folders ?? [];
  const addExtra = (dir: string): void => {
    if (dir !== row?.device_game_folder && !extras.includes(dir)) edit({ device_extra_folders: [...extras, dir] });
  };

  async function save(next: DeviceConsole | null | undefined = row, done = "Saved"): Promise<void> {
    if (!currentDeviceId || !next?.id) return;
    setSaving(true);
    setMsg("");
    try {
      const { id: _id, console_name: _name, ...folders } = next;
      const body: Folders = { ...folders };
      // The copy destination defaults to the ROM folder; store that so Move/Network panels see it,
      // and keep it following the ROM folder while it still equals the folder it was defaulted from.
      if (body.device_network_folder && (!body.device_local_folder || body.device_local_folder === origRom)) body.device_local_folder = body.device_game_folder;
      await updateDeviceConsole(currentDeviceId, next.id, body);
      setOrigRom(body.device_game_folder);
      setMsg(done);
    } catch {
      setMsg("Couldn't save — is the server reachable?");
    } finally {
      setSaving(false);
    }
  }

  // Console-wide emulator switch (#753): rebuild every game on this console here
  // (Custom-command games are left alone), then store the console's emulator + folders.
  const emuValue = emu.options.find((o) => o.label === row?.device_emulator)?.id ?? "";
  async function pickEmulator(id: string): Promise<void> {
    const option = emu.options.find((o) => o.id === id);
    if (!option) return;
    setSwitching(true);
    try {
      setPending({ id, ...(await previewConsoleSwitch(abbr, consoleKey, option, emu.options)) });
    } catch {
      setMsg("Couldn't load this console's games — is the server reachable?");
    } finally {
      setSwitching(false);
    }
  }
  async function confirmSwitch(move: boolean): Promise<void> {
    const option = emu.options.find((o) => o.id === pending?.id);
    if (!pending || !option || !row) return;
    setSwitching(true);
    let res: Awaited<ReturnType<typeof applyConsoleSwitch>>;
    try {
      res = await applyConsoleSwitch(pending.items, move);
    } catch {
      setMsg("Switch failed part-way — is the server reachable? Reopen to check each game.");
      return;
    } finally {
      setPending(null);
      setSwitching(false);
    }
    // Console folders are the emulator roots without RetroArch's core folder,
    // matching scan.ts:resolveRomEntry and netplay.ts (GameName/... is appended).
    const root = (dir = ""): string => (option.coreFolderName && dir ? dir.replace(/[\\/][^\\/]*[\\/]?$/, "") : dir);
    const card = usesSharedSaveLayout(abbr) ? pending.items[0]?.plan.savePath : "";
    const next = { ...row, device_emulator: option.label, device_save_folder: card || root(option.saveDir), device_state_folder: root(option.stateDir) };
    setRow(next);
    const parts = [`Switched ${res.updated} game${res.updated === 1 ? "" : "s"} to ${option.label}`];
    if (res.moved) parts.push(`${res.moved} save file${res.moved === 1 ? "" : "s"} moved`);
    if (res.skipped.length) parts.push(`${res.skipped.length} kept because a file already exists at the new location`);
    if (res.errors.length) parts.push(`failed: ${res.errors.join("; ")}`);
    await save(next, parts.join(", ") + ".");
  }
  const sample = pending?.items.find((i) => pathsChanged(i.plan));

  return (
    <Modal size="md" onClose={onClose}>
        <h3>{abbr || consoleKey} settings on this device</h3>
        {row === undefined ? (
          <span className="spinner" />
        ) : row === null && loadFailed ? (
          <p>Couldn't load this console's folders — is the server reachable?</p>
        ) : row === null ? (
          <p>No folders recorded for this console yet. They are learned when you import or configure a game.</p>
        ) : (
          <div className="config-form" style={{ marginBottom: 16 }}>
            {usesSharedSaveLayout(abbr) && (
              <p style={{ color: "var(--text-muted)", fontSize: 12 }}>This console shares one memory card across games; the save folder is the card location.</p>
            )}
            {FIELDS.map((f) => (
              <div key={f.key} className="input-group">
                <label htmlFor={`cf-${f.key}`}>{f.label}</label>
                <div style={{ display: "flex", gap: 6 }}>
                  <input id={`cf-${f.key}`} type="text" value={row[f.key] ?? ""}
                    onChange={(e) => edit({ [f.key]: e.target.value })} style={{ flex: 1 }} />
                  <button className="btn btn-ghost" onClick={() => browse((d) => edit({ [f.key]: d }))}>Browse</button>
                </div>
              </div>
            ))}
            <div className="input-group">
              <label htmlFor="cf-emulator">Emulator</label>
              <EmulatorPicker id="cf-emulator" emu={emu} value={emuValue} onChange={pickEmulator} allowCustom={false} disabled={switching} />
              {row.device_emulator && !emuValue && emu.loaded && (
                <p style={{ color: "var(--text-muted)", fontSize: 12 }}>Saved: {row.device_emulator} (not detected on this device)</p>
              )}
            </div>
            <div className="input-group">
              <label htmlFor="cf-device_network_folder">Network (NAS) folder</label>
              <div style={{ display: "flex", gap: 6 }}>
                <input id="cf-device_network_folder" type="text" value={row.device_network_folder ?? ""}
                  onChange={(e) => edit({ device_network_folder: e.target.value })} style={{ flex: 1 }} />
                <button className="btn btn-ghost" onClick={() => browse((d) => edit({ device_network_folder: d }))}>Browse</button>
              </div>
            </div>
            {row.device_network_folder && (
              <div className="input-group">
                <label htmlFor="cf-device_local_folder">Copy network ROMs to</label>
                <div style={{ display: "flex", gap: 6 }}>
                  <input id="cf-device_local_folder" type="text" value={row.device_local_folder ?? ""}
                    placeholder={row.device_game_folder} onChange={(e) => edit({ device_local_folder: e.target.value })} style={{ flex: 1 }} />
                  <button className="btn btn-ghost" onClick={() => browse((d) => edit({ device_local_folder: d }))}>Browse</button>
                </div>
                <p style={{ color: "var(--text-muted)", fontSize: 12 }}>Blank uses the ROM folder.</p>
              </div>
            )}
            <div className="input-group">
              <label>Other ROM folders</label>
              {extras.map((f) => (
                <div key={f} style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 4 }}>
                  <span style={{ flex: 1, overflowWrap: "anywhere" }}>{f}</span>
                  <button className="btn btn-ghost" onClick={() => edit({ device_extra_folders: extras.filter((x) => x !== f) })}>Remove</button>
                </div>
              ))}
              {legacy.map((f) => (
                <div key={f} style={{ marginBottom: 4, color: "var(--text-muted)", overflowWrap: "anywhere" }}>{f} (from an earlier import)</div>
              ))}
              <div><button className="btn btn-ghost" onClick={() => browse(addExtra)}>Add folder</button></div>
              <p style={{ color: "var(--text-muted)", fontSize: 12 }}>
                Games found in a folder not listed here are added to this list automatically.
              </p>
            </div>
            <div className="modal-actions">
              <button className="btn btn-primary" disabled={saving} onClick={() => save()}>
                {saving ? <><span className="spinner" /> Saving…</> : "Save"}
              </button>
            </div>
          </div>
        )}
        {pending && (
          <EmulatorSwitchModal
            fromLabel={row?.device_emulator ?? ""}
            toLabel={emu.options.find((o) => o.id === pending.id)?.label ?? ""}
            savePath={sample && sample.plan.savePath !== sample.plan.fromSave ? sample.plan.savePath : undefined}
            statePath={sample && sample.plan.statePath !== sample.plan.fromState ? sample.plan.statePath : undefined}
            note={`Applies to ${pending.items.length} game${pending.items.length === 1 ? "" : "s"} on this device${pending.customCount ? ` (${pending.customCount} with a custom command left as is)` : ""}.${sample && pending.items.length > 1 ? ` Paths shown for ${sample.name}.` : ""}`}
            busy={switching}
            onCancel={() => setPending(null)}
            onConfirm={confirmSwitch}
          />
        )}
        <IgnoredGamesPanel consoleKey={consoleKey} />
        {msg && <p style={{ color: "var(--text-muted)", fontSize: 12 }}>{msg}</p>}
        <div className="modal-actions">
          <button className="btn btn-ghost" onClick={onClose}>Close</button>
        </div>
      </Modal>
  );
}
