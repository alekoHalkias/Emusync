// Paired-devices list, rendered as a section inside the Server modal (issue #262).
// Extracted from the old standalone DevicesButton; no trigger button / overlay of
// its own — it relies on the host modal for that.
import React, { useCallback, useEffect, useState } from "react";
import { listEvents, removeDevice, type ActivityEvent } from "../api";
import { RelTime } from "../time";
import { useDevices } from "../DeviceContext";

export default function DevicesPanel(): React.ReactElement {
  const { devices, currentDeviceId, refresh } = useDevices();
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [eventsLoading, setEventsLoading] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState<string | null>(null);
  const [removing, setRemoving] = useState(false);

  const loadEvents = useCallback(async () => {
    setEventsLoading(true);
    try {
      setEvents(await listEvents());
    } catch {
      setEvents([]);
    } finally {
      setEventsLoading(false);
    }
  }, []);

  useEffect(() => { loadEvents(); }, [loadEvents]);

  const getLastSync = (deviceId: string): string | null => {
    const syncEvents = events.filter(
      e => e.device_id === deviceId && (e.type === "save_synced" || e.type === "state_synced"),
    );
    return syncEvents.length === 0 ? null : syncEvents[0].occurred_at;
  };

  async function handleRemoveDevice(): Promise<void> {
    if (!confirmRemove) return;
    setRemoving(true);
    try {
      await removeDevice(confirmRemove);
      setConfirmRemove(null);
      await refresh();
    } catch {
      /* error — keep UI responsive */
    } finally {
      setRemoving(false);
    }
  }

  return (
    <div style={{ marginTop: 20, borderTop: "1px solid var(--border)", paddingTop: 16 }}>
      <h4 style={{ margin: "0 0 12px" }}>Paired devices ({devices.length})</h4>

      {eventsLoading ? (
        <div style={{ textAlign: "center", padding: "20px 0" }}>
          <span className="spinner" style={{ width: 20, height: 20 }} />
        </div>
      ) : devices.length === 0 ? (
        <p style={{ color: "var(--text-muted)" }}>No devices paired yet</p>
      ) : (
        <div>
          {devices.map(d => (
            <div
              key={d.id}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "12px",
                background: "var(--surface2)",
                borderRadius: 6,
                marginBottom: 8,
                fontSize: 13,
              }}
            >
              <div>
                <div style={{ fontWeight: 500, marginBottom: 2 }}>{d.name}</div>
                <div style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "monospace" }}>
                  {d.id.slice(0, 12)}…
                </div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <div style={{ textAlign: "right", color: "var(--text-muted)", fontSize: 12 }}>
                  {getLastSync(d.id)
                    ? <>
                        <div style={{ marginBottom: 2 }}>Last sync</div>
                        <div><RelTime iso={getLastSync(d.id)} /></div>
                      </>
                    : "Never synced"}
                </div>
                <button
                  className="btn btn-icon"
                  title={d.id === currentDeviceId ? "Cannot remove this device" : "Remove device"}
                  disabled={d.id === currentDeviceId}
                  onClick={() => setConfirmRemove(d.id)}
                >
                  🗑
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {confirmRemove && (
        <div className="modal-overlay" onClick={() => setConfirmRemove(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Remove device?</h3>
            <p>This device will be removed from your paired devices. It can re-pair anytime.</p>
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setConfirmRemove(null)} disabled={removing}>
                Cancel
              </button>
              <button className="btn btn-danger" onClick={handleRemoveDevice} disabled={removing}>
                {removing ? <><span className="spinner" /> Removing…</> : "Remove"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
