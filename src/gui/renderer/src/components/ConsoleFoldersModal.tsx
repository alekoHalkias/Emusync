// Per-console settings editor for this device (#539, #629). One block per console:
// folders live on its primary `consoles` row, extra ROM folders in
// `device_extra_folders`; older one-row-per-folder entries are listed read-only.
import React, { useEffect, useState } from "react";
import { getDeviceConsoles, updateDeviceConsole, type DeviceConsole } from "../api";
import { useDevices } from "../DeviceContext";
import { usesSharedSaveLayout } from "./console-import/helpers";
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
  const [emulators, setEmulators] = useState<string[]>([]);
  const [abbr, setAbbr] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    if (!currentDeviceId) return;
    (async () => {
      const defs = (await window.emusync.emulator.consoles().catch(() => [])) ?? [];
      const a = defs.find((d) => d.key === consoleKey)?.abbr ?? consoleKey;
      setAbbr(a);
      const all = (await getDeviceConsoles(currentDeviceId).catch(() => [])).filter((c) => c.console_name.toLowerCase() === a.toLowerCase());
      const primary = all.find((c) => c.device_game_folder) ?? all[0] ?? null;
      setRow(primary);
      setOrigRom(primary?.device_game_folder ?? "");
      setLegacy(all.filter((c) => c !== primary && c.device_game_folder).map((c) => c.device_game_folder));
      const det = await window.emusync.emulator.detect(consoleKey).catch(() => null);
      setEmulators([...new Set((det?.options ?? []).map((o: { label: string }) => o.label))]);
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

  async function save(): Promise<void> {
    if (!currentDeviceId || !row?.id) return;
    setSaving(true);
    setMsg("");
    try {
      const { id: _id, console_name: _name, ...folders } = row;
      const body: Folders = { ...folders };
      // The copy destination defaults to the ROM folder; store that so Move/Network panels see it,
      // and keep it following the ROM folder while it still equals the folder it was defaulted from.
      if (body.device_network_folder && (!body.device_local_folder || body.device_local_folder === origRom)) body.device_local_folder = body.device_game_folder;
      await updateDeviceConsole(currentDeviceId, row.id, body);
      setOrigRom(body.device_game_folder);
      setMsg("Saved");
    } catch {
      setMsg("Couldn't save — is the server reachable?");
    } finally {
      setSaving(false);
    }
  }

  const emuChoices = row?.device_emulator && !emulators.includes(row.device_emulator) ? [row.device_emulator, ...emulators] : emulators;

  return (
    <Modal size="md" onClose={onClose}>
        <h3>{abbr || consoleKey} settings on this device</h3>
        {row === undefined ? (
          <span className="spinner" />
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
              <select id="cf-emulator" value={row.device_emulator} onChange={(e) => edit({ device_emulator: e.target.value })}>
                <option value="">Not set</option>
                {emuChoices.map((l) => <option key={l} value={l}>{l}</option>)}
              </select>
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
              <button className="btn btn-primary" disabled={saving} onClick={save}>
                {saving ? <><span className="spinner" /> Saving…</> : "Save"}
              </button>
            </div>
          </div>
        )}
        {msg && <p style={{ color: "var(--text-muted)", fontSize: 12 }}>{msg}</p>}
        <div className="modal-actions">
          <button className="btn btn-ghost" onClick={onClose}>Close</button>
        </div>
      </Modal>
  );
}
