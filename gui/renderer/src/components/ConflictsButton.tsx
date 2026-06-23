import React, { useCallback, useEffect, useState } from "react";
import {
  listConflicts, dismissConflict, listSaveHistory, restoreSave, getGameDevice,
  type SaveConflict,
} from "../api";
import { RelTime } from "../time";

/**
 * Top-bar "Conflicts" panel (issue #243). EmuSync auto-resolves a true save
 * divergence newest-wins and records it on the server; this lists the open ones
 * and lets the user recover the losing copy.
 *
 * Recovery reuses the existing save history/restore: the loser is found in the
 * game's history by hash and restored (made current), then written to this device
 * if it has the game. When the *server* won, the loser was this device's pre-pull
 * copy, which lives only as a local .bak and isn't in server history — that case
 * is detected and the user is pointed at the .bak instead.
 */
export default function ConflictsButton(): React.ReactElement | null {
  const [conflicts, setConflicts] = useState<SaveConflict[]>([]);
  const [open, setOpen] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [status, setStatus] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    try {
      setConflicts(await listConflicts());
    } catch {
      /* server may be down — keep last known */
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 20000);
    return () => clearInterval(t);
  }, [load]);

  const deviceName = (c: SaveConflict, which: "winner" | "loser"): string =>
    (which === "winner" ? c.winner_device_name : c.loser_device_name)
    || (which === "winner" ? c.winner_device_id : c.loser_device_id).slice(0, 8)
    || "a device";

  async function handleRecover(c: SaveConflict): Promise<void> {
    setBusyId(c.id);
    setStatus(s => ({ ...s, [c.id]: "" }));
    try {
      const history = await listSaveHistory(c.game_slug);
      const loser = c.loser_hash ? history.find(v => v.hash === c.loser_hash) : undefined;
      if (!loser) {
        setStatus(s => ({
          ...s,
          [c.id]: `The ${deviceName(c, "loser")} copy isn't on the server — it was kept as a ` +
            `.bak file next to the save on that device. Restore it from there.`,
        }));
        return;
      }
      await restoreSave(c.game_slug, loser.id);
      // Write the now-current (recovered) save to this device if it has the game.
      let wrote = false;
      try {
        const gd = await getGameDevice(c.game_slug);
        if (gd?.save_path) {
          const res = await window.emusync.save.pull(c.game_slug, gd.save_path);
          if (!res.ok) throw new Error(res.error || "wrote on server, but not to this device");
          wrote = true;
        }
      } catch {
        /* game not configured locally — server restore still stands */
      }
      await dismissConflict(c.id);
      setStatus(s => ({
        ...s,
        [c.id]: wrote
          ? "Recovered and written to this device (previous save kept as .bak)."
          : "Recovered on the server — it will reach this device on the next launch/sync.",
      }));
      await load();
    } catch (e: any) {
      setStatus(s => ({ ...s, [c.id]: e?.message || "Recovery failed" }));
    } finally {
      setBusyId(null);
    }
  }

  async function handleDismiss(c: SaveConflict): Promise<void> {
    setBusyId(c.id);
    try {
      await dismissConflict(c.id);
      await load();
    } catch {
      /* leave it visible if dismissal failed */
    } finally {
      setBusyId(null);
    }
  }

  // The button is exceptional UI — only show it when there's something to resolve.
  if (conflicts.length === 0 && !open) return null;

  return (
    <>
      <button
        className="btn btn-ghost"
        onClick={() => setOpen(true)}
        style={{ fontSize: 13, color: conflicts.length ? "var(--red)" : undefined }}
        title="Save conflicts to review"
      >
        ⚠ Conflicts {conflicts.length}
      </button>

      {open && (
        <div className="modal-overlay" onClick={() => setOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ width: 520 }}>
            <h3 style={{ marginBottom: 4 }}>Save conflicts</h3>
            <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 0 }}>
              Both copies of a save changed since the last sync. EmuSync kept the newer one;
              you can recover the other version here.
            </p>

            {conflicts.length === 0 ? (
              <p style={{ color: "var(--text-muted)", padding: "12px 0" }}>No conflicts to review. 🎉</p>
            ) : (
              <ul style={{ listStyle: "none", padding: 0, margin: "8px 0 0" }}>
                {conflicts.map(c => (
                  <li key={c.id} style={{ padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
                    <div style={{ fontWeight: 500 }}>{c.game_name}</div>
                    <div style={{ fontSize: 12, color: "var(--text-muted)", margin: "2px 0 8px" }}>
                      <RelTime iso={c.resolved_at} /> · kept {deviceName(c, "winner")}'s save;
                      {" "}{deviceName(c, "loser")}'s copy was replaced
                    </div>
                    <div style={{ display: "flex", gap: 8 }}>
                      <button
                        className="btn btn-ghost"
                        style={{ fontSize: 12, padding: "3px 10px" }}
                        disabled={busyId !== null}
                        onClick={() => handleRecover(c)}
                      >
                        {busyId === c.id
                          ? <><span className="spinner" style={{ width: 12, height: 12, marginRight: 6 }} />Working…</>
                          : `Recover ${deviceName(c, "loser")} version`}
                      </button>
                      <button
                        className="btn btn-ghost"
                        style={{ fontSize: 12, padding: "3px 10px" }}
                        disabled={busyId !== null}
                        onClick={() => handleDismiss(c)}
                      >
                        Dismiss
                      </button>
                    </div>
                    {status[c.id] && (
                      <p style={{ fontSize: 11, color: "var(--text-muted)", margin: "8px 0 0" }}>{status[c.id]}</p>
                    )}
                  </li>
                ))}
              </ul>
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
