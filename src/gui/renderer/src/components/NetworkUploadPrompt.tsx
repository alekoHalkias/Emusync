import React, { useEffect, useState } from "react";
import { listDevices, listPendingPullRequests, type Device, type PullRequestRow } from "../api";

/**
 * Banner for network-upload requests (#660) the sync-daemon left pending because
 * the ROM is over `network_upload_auto_max_mb`. Upload / Decline shell out to the
 * CLI via `rom:fulfillNetworkUpload`; declining reports a failed request back.
 */
export default function NetworkUploadPrompt(): React.ReactElement | null {
  const [rows, setRows] = useState<PullRequestRow[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [pending, devs] = await Promise.all([listPendingPullRequests(), listDevices().catch(() => [] as Device[])]);
        setRows(pending.filter((r) => r.kind === "network-upload"));
        setDevices(devs);
      } catch { /* server unreachable: nothing to ask about */ }
    })();
  }, []);

  async function answer(id: string, approve: boolean): Promise<void> {
    setBusyId(id);
    setError(null);
    const res = await window.emusync.rom.fulfillNetworkUpload(id, approve);
    setBusyId(null);
    if (res.ok) setRows((prev) => prev.filter((r) => r.id !== id));
    else setError(res.error ?? "Upload failed");
  }

  if (rows.length === 0) return null;
  return (
    <>
      {rows.map((r) => (
        <div
          key={r.id}
          style={{
            background: "var(--surface2)", color: "var(--text)", fontSize: 12, padding: "8px 16px",
            display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8,
            borderBottom: "1px solid var(--border)",
          }}
        >
          <span>
            <strong>{devices.find((d) => d.id === r.to_device_id)?.name ?? "Another device"}</strong> asked to
            upload <strong>{r.game_name}</strong> to the network drive.
            {error && busyId === null && <span style={{ color: "var(--color-danger, #e5484d)", marginLeft: 8 }}>{error}</span>}
          </span>
          <div style={{ display: "flex", gap: 6 }}>
            <button className="btn" style={{ fontSize: 11, padding: "3px 10px" }} disabled={busyId !== null} onClick={() => answer(r.id, true)}>
              {busyId === r.id ? <span className="spinner" style={{ width: 10, height: 10 }} /> : "Upload"}
            </button>
            <button className="btn btn-ghost" style={{ fontSize: 11, padding: "3px 8px" }} disabled={busyId !== null} onClick={() => answer(r.id, false)}>
              Decline
            </button>
          </div>
        </div>
      ))}
    </>
  );
}
