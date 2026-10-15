// Per-console folder editor for this device (#539). The fields live on the
// existing `consoles` rows; before this they could only be set by importing.
import React, { useEffect, useState } from "react";
import { getDeviceConsoles, updateDeviceConsole, type DeviceConsole } from "../api";
import { useDevices } from "../DeviceContext";
import { useEscapeToClose } from "../useEscapeToClose";
import { usesSharedSaveLayout } from "./console-import/helpers";

type Folders = Omit<DeviceConsole, "id" | "console_name">;
const FIELDS: Array<{ key: keyof Folders; label: string; picker: boolean }> = [
  { key: "device_game_folder", label: "ROM folder", picker: true },
  { key: "device_save_folder", label: "Save folder", picker: true },
  { key: "device_state_folder", label: "States folder", picker: true },
  { key: "device_emulator", label: "Emulator", picker: false },
  { key: "device_network_folder", label: "Network (NAS) folder", picker: true },
  { key: "device_local_folder", label: "Local copy folder", picker: true },
];

type Props = { consoleKey: string; onClose: () => void };

export default function ConsoleFoldersModal({ consoleKey, onClose }: Props): React.ReactElement {
  const { currentDeviceId } = useDevices();
  const [rows, setRows] = useState<DeviceConsole[] | null>(null);
  const [abbr, setAbbr] = useState("");
  const [saving, setSaving] = useState<string | null>(null);
  const [msg, setMsg] = useState("");
  useEscapeToClose(onClose);

  useEffect(() => {
    if (!currentDeviceId) return;
    (async () => {
      const defs = (await window.emusync.emulator.consoles().catch(() => [])) ?? [];
      const a = defs.find((d) => d.key === consoleKey)?.abbr ?? consoleKey;
      setAbbr(a);
      const all = await getDeviceConsoles(currentDeviceId).catch(() => []);
      setRows(all.filter((c) => c.console_name.toLowerCase() === a.toLowerCase()));
    })();
  }, [currentDeviceId, consoleKey]);

  function edit(id: string | undefined, key: keyof Folders, value: string): void {
    setRows((rs) => rs && rs.map((r) => (r.id === id ? { ...r, [key]: value } : r)));
  }

  async function browse(id: string | undefined, key: keyof Folders): Promise<void> {
    const dir = await window.emusync.dialog.openFolder();
    if (dir) edit(id, key, dir);
  }

  async function save(row: DeviceConsole): Promise<void> {
    if (!currentDeviceId || !row.id) return;
    setSaving(row.id);
    setMsg("");
    try {
      const { id: _id, console_name: _name, ...folders } = row;
      await updateDeviceConsole(currentDeviceId, row.id, folders);
      setMsg("Saved");
    } catch {
      setMsg("Couldn't save — is the server reachable?");
    } finally {
      setSaving(null);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ width: 560 }} onClick={(e) => e.stopPropagation()}>
        <h3>{abbr || consoleKey} folders on this device</h3>
        {rows === null ? (
          <span className="spinner" />
        ) : rows.length === 0 ? (
          <p>No folders recorded for this console yet. They are learned when you import or configure a game.</p>
        ) : (
          rows.map((row) => (
            <div key={row.id} className="config-form" style={{ marginBottom: 16 }}>
              {usesSharedSaveLayout(abbr) && (
                <p style={{ color: "var(--text-muted)", fontSize: 12 }}>This console shares one memory card across games; the save folder is the card location.</p>
              )}
              {FIELDS.map((f) => (
                <div key={f.key} className="input-group">
                  <label htmlFor={`${row.id}-${f.key}`}>{f.label}</label>
                  <div style={{ display: "flex", gap: 6 }}>
                    <input id={`${row.id}-${f.key}`}
                      type="text"
                      value={(row[f.key] as string | undefined) ?? ""}
                      onChange={(e) => edit(row.id, f.key, e.target.value)}
                      style={{ flex: 1 }}
                    />
                    {f.picker && <button className="btn btn-ghost" onClick={() => browse(row.id, f.key)}>Browse</button>}
                  </div>
                </div>
              ))}
              <p style={{ color: "var(--text-muted)", fontSize: 12 }}>
                Changing the ROM folder starts a new entry the next time a game is imported from the old folder.
              </p>
              <div className="modal-actions">
                <button className="btn btn-primary" disabled={saving === row.id} onClick={() => save(row)}>
                  {saving === row.id ? <><span className="spinner" /> Saving…</> : "Save"}
                </button>
              </div>
            </div>
          ))
        )}
        {msg && <p style={{ color: "var(--text-muted)", fontSize: 12 }}>{msg}</p>}
        <div className="modal-actions">
          <button className="btn btn-ghost" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}
