import React, { useEffect, useState } from "react";
import { listSaveHistory, restoreSave, type SaveVersion } from "../api";
import { useDevices } from "../DeviceContext";

type Props = {
  slug: string;
  name: string;
  /** This device's local save path; required to write a restored version to disk. */
  savePath?: string;
  onClose: () => void;
  onRestored: () => void;
};

function fmtSize(n: number): string {
  if (n == null) return "?";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

/**
 * Per-game save history with rollback (issue #7). Lists every retained save
 * generation; restoring makes that version current on the server and, when this
 * device has the game locally, writes it to disk (the replaced file is kept as
 * .bak by the existing save:pull handler).
 */
export default function SaveHistory({ slug, name, savePath, onClose, onRestored }: Props): React.ReactElement {
  const { devices } = useDevices();
  const [versions, setVersions] = useState<SaveVersion[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [restoringId, setRestoringId] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const deviceName = (id: string): string => devices.find(d => d.id === id)?.name ?? id.slice(0, 8);

  useEffect(() => {
    listSaveHistory(slug)
      .then(setVersions)
      .catch(e => { setError(e.message || "Failed to load history"); setVersions([]); });
  }, [slug]);

  async function handleRestore(v: SaveVersion): Promise<void> {
    setRestoringId(v.id);
    setStatus(null);
    try {
      await restoreSave(slug, v.id);
      // Write the now-current version to this device's disk if it has one.
      if (savePath) {
        const res = await (window as any).emusync.save.pull(slug, savePath);
        if (!res.ok) throw new Error(res.error || "Restored on server, but failed to write locally");
        setStatus("Restored and written to this device (previous save kept as .bak).");
      } else {
        setStatus("Restored on the server. It will reach this device on the next launch/sync.");
      }
      const refreshed = await listSaveHistory(slug);
      setVersions(refreshed);
      onRestored();
    } catch (e: any) {
      setStatus(e.message || "Restore failed");
    } finally {
      setRestoringId(null);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ width: 540 }} onClick={(e) => e.stopPropagation()}>
        <h3>Save history — {name}</h3>
        {versions === null ? (
          <div style={{ textAlign: "center", padding: "16px 0" }}>
            <span className="spinner" style={{ width: 20, height: 20 }} />
          </div>
        ) : error && versions.length === 0 ? (
          <p style={{ color: "var(--red)" }}>{error}</p>
        ) : versions.length === 0 ? (
          <p style={{ color: "var(--text-muted)" }}>No save history yet for this game.</p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0, margin: "8px 0 0" }}>
            {versions.map((v, i) => (
              <li key={v.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13 }}>
                    {v.pushed_at.slice(0, 19).replace("T", " ")}
                    {i === 0 && <span style={{ color: "var(--green)", marginLeft: 8, fontSize: 11 }}>current</span>}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                    {fmtSize(v.size)} · from {deviceName(v.device_id)}
                  </div>
                </div>
                <button
                  className="btn btn-ghost"
                  style={{ fontSize: 12, padding: "3px 10px" }}
                  disabled={i === 0 || restoringId !== null}
                  title={i === 0 ? "This is the current save" : "Roll back to this version"}
                  onClick={() => handleRestore(v)}
                >
                  {restoringId === v.id ? <><span className="spinner" style={{ width: 12, height: 12, marginRight: 6 }} />Restoring…</> : "Restore"}
                </button>
              </li>
            ))}
          </ul>
        )}
        {status && <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 12 }}>{status}</p>}
        <div className="modal-actions">
          <button className="btn btn-ghost" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}
