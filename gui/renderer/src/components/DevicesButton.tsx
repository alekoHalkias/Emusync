import React, { useCallback, useEffect, useState } from "react";
import { listDevices, listEvents, type Device, type ActivityEvent } from "../api";

export default function DevicesButton(): React.ReactElement {
  const [open, setOpen] = useState(false);
  const [devices, setDevices] = useState<Device[]>([]);
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [devs, evts] = await Promise.all([listDevices(), listEvents()]);
      setDevices(devs);
      setEvents(evts);
    } catch {
      setDevices([]);
      setEvents([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  const getLastSync = (deviceId: string): string | null => {
    const syncEvents = events.filter(e => e.device_id === deviceId && (e.type === "save_synced" || e.type === "state_synced"));
    if (syncEvents.length === 0) return null;
    return syncEvents[0].occurred_at.slice(0, 19);
  };

  return (
    <>
      <button
        className="btn btn-ghost"
        onClick={() => setOpen(true)}
        style={{ fontSize: 13 }}
        title="View paired devices"
      >
        📱 {devices.length}
      </button>

      {open && (
        <div className="modal-overlay" onClick={() => setOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ width: 450 }}>
            <h3 style={{ marginBottom: 16 }}>Paired devices ({devices.length})</h3>

            {loading ? (
              <div style={{ textAlign: "center", padding: "20px 0" }}>
                <span className="spinner" style={{ width: 20, height: 20 }} />
              </div>
            ) : devices.length === 0 ? (
              <p style={{ color: "var(--text-muted)", marginBottom: 20 }}>No devices paired yet</p>
            ) : (
              <div style={{ marginBottom: 20 }}>
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
                    <div style={{ textAlign: "right", color: "var(--text-muted)", fontSize: 12 }}>
                      {getLastSync(d.id)
                        ? <>
                            <div style={{ marginBottom: 2 }}>Last sync</div>
                            <div>{getLastSync(d.id)}</div>
                          </>
                        : "Never synced"}
                    </div>
                  </div>
                ))}
              </div>
            )}

            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setOpen(false)}>Close</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
