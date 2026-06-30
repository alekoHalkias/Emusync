import React, { useEffect, useState } from "react";
import {
  listSaveHistory, restoreSave, listStateHistory, restoreState,
  getGameIntegrity, type SaveVersion, type GameIntegrity, type BlobIntegrity, type IntegrityReason,
} from "../api";
import { RelTime } from "../time";
import { useDevices } from "../DeviceContext";

type Kind = "save" | "state";

type Props = {
  slug: string;
  name: string;
  /** This device's local save path; required to write a restored save to disk. */
  savePath?: string;
  /** This device's local state FOLDER; required to write a restored state to disk. */
  statePath?: string;
  onClose: () => void;
  onRestored: () => void;
  embedded?: boolean;            // rendered inside the tabbed game modal (#260)
};

/** One row in the merged recovery timeline: a server generation or a local .bak. */
type Entry = {
  source: "server" | "local-bak";
  kind: Kind;
  key: string;
  ts: string;
  size: number;
  deviceId?: string;            // server only
  isCurrent?: boolean;          // newest server generation of its kind
  damaged?: BlobIntegrity;      // set on the current entry when flagged
  versionId?: string;          // server restore target
  bakPath?: string;            // local-bak only
  targetPath?: string;         // where a local-bak restores to
};

function fmtSize(n: number | null): string {
  if (n == null) return "?";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

const REASON_TEXT: Record<IntegrityReason, string> = {
  zero_byte: "the file is empty",
  shrank: "it is much smaller than the previous version",
  hash_mismatch: "its contents don't match the recorded checksum",
  file_missing: "the stored file is missing",
};

function reasonsText(reasons: IntegrityReason[]): string {
  return reasons.map(r => REASON_TEXT[r] ?? r).join("; ");
}

/**
 * Per-game recovery view (issues #7 + #285). Merges server save/state history
 * generations with local on-disk `.bak` losers into one timeline, flags a
 * damaged current blob (0-byte / truncated / checksum-mismatch), and offers a
 * one-click "restore last good". Restoring a server version makes it current and
 * (when the game is local) writes it to disk; restoring a `.bak` recovers a copy
 * that may never have reached the server. Nothing is auto-acted on.
 */
export default function SaveHistory({ slug, name, savePath, statePath, onClose, onRestored, embedded }: Props): React.ReactElement {
  const { devices } = useDevices();
  const [entries, setEntries] = useState<Entry[] | null>(null);
  const [integrity, setIntegrity] = useState<GameIntegrity | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const deviceName = (id: string): string => devices.find(d => d.id === id)?.name ?? id.slice(0, 8);
  const localPathFor = (k: Kind): string | undefined => (k === "save" ? savePath : statePath);

  async function load(): Promise<void> {
    try {
      const [saveHist, stateHist, integ, baks] = await Promise.all([
        listSaveHistory(slug).catch(() => [] as SaveVersion[]),
        listStateHistory(slug).catch(() => [] as SaveVersion[]),
        getGameIntegrity(slug).catch(() => null),
        window.emusync.recovery.listLocalBackups(savePath ?? "", statePath ?? "").catch(() => ({ saves: [], states: [] })),
      ]);
      setIntegrity(integ);

      const merged: Entry[] = [];
      const addServer = (kind: Kind, hist: SaveVersion[], verdict?: BlobIntegrity): void => {
        hist.forEach((v, i) => {
          const isCurrent = i === 0;
          merged.push({
            source: "server", kind, key: `s-${kind}-${v.id}`,
            ts: v.pushed_at, size: v.size, deviceId: v.device_id,
            isCurrent, versionId: v.id,
            damaged: isCurrent && verdict?.status === "damaged" ? verdict : undefined,
          });
        });
      };
      addServer("save", saveHist, integ?.save);
      addServer("state", stateHist, integ?.state);

      const addBaks = (kind: Kind, list: { path: string; size: number; mtime: string }[]): void => {
        for (const b of list) {
          merged.push({
            source: "local-bak", kind, key: `b-${b.path}`,
            ts: b.mtime, size: b.size,
            bakPath: b.path, targetPath: b.path.replace(/\.bak$/, ""),
          });
        }
      };
      addBaks("save", baks.saves);
      addBaks("state", baks.states);

      merged.sort((a, b) => (a.ts < b.ts ? 1 : a.ts > b.ts ? -1 : 0));
      setEntries(merged);
    } catch (e: any) {
      setError(e.message || "Failed to load history");
      setEntries([]);
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [slug]);

  /** Restore a server generation (the current "restore last good" or an older row). */
  async function restoreServer(kind: Kind, versionId: string, key: string): Promise<void> {
    setBusyKey(key);
    setStatus(null);
    try {
      if (kind === "save") await restoreSave(slug, versionId);
      else await restoreState(slug, versionId);
      const local = localPathFor(kind);
      if (local) {
        const res = kind === "save"
          ? await window.emusync.save.pull(slug, local)
          : await window.emusync.state.pull(slug, local);
        if (!res.ok) throw new Error(res.error || "Restored on server, but failed to write locally");
        setStatus(`Restored and written to this device (previous ${kind} kept as .bak).`);
      } else {
        setStatus("Restored on the server. It will reach this device on the next launch/sync.");
      }
      onRestored();
      await load();
    } catch (e: any) {
      setStatus(e.message || "Restore failed");
    } finally {
      setBusyKey(null);
    }
  }

  /** Recover a local .bak loser that may never have reached the server. */
  async function restoreBak(e: Entry): Promise<void> {
    if (!e.bakPath || !e.targetPath) return;
    setBusyKey(e.key);
    setStatus(null);
    try {
      const res = await window.emusync.recovery.restoreLocalBackup(e.bakPath, e.targetPath);
      if (!res.ok) throw new Error(res.error || "Restore failed");
      setStatus("Local backup restored to disk. Use ▶ or push to put it on the server.");
      onRestored();
      await load();
    } catch (err: any) {
      setStatus(err.message || "Restore failed");
    } finally {
      setBusyKey(null);
    }
  }

  function renderRow(e: Entry): React.ReactElement {
    const busy = busyKey !== null;
    const restoring = busyKey === e.key;
    const kindTag = (
      <span style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 0.4, color: "var(--text-muted)", border: "1px solid var(--border)", borderRadius: 3, padding: "1px 4px", marginRight: 6 }}>
        {e.kind}
      </span>
    );
    return (
      <li key={e.key} style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13 }}>
            {kindTag}
            <RelTime iso={e.ts} />
            {e.isCurrent && !e.damaged && <span style={{ color: "var(--green)", marginLeft: 8, fontSize: 11 }}>current</span>}
            {e.damaged && (
              <span style={{ color: "var(--red)", marginLeft: 8, fontSize: 11 }} title={`This save looks damaged: ${reasonsText(e.damaged.reasons)}.`}>
                ⚠ damaged
              </span>
            )}
            {e.source === "local-bak" && <span style={{ color: "var(--text-muted)", marginLeft: 8, fontSize: 11 }}>local backup (not on server)</span>}
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
            {fmtSize(e.size)}
            {e.deviceId ? ` · from ${deviceName(e.deviceId)}` : ""}
            {e.source === "local-bak" ? ` · ${e.bakPath}` : ""}
          </div>
        </div>

        {/* Damaged current → prominent "restore last good"; otherwise the per-row action. */}
        {e.damaged ? (
          e.damaged.last_good_version_id ? (
            <button
              className="btn"
              style={{ fontSize: 12, padding: "3px 10px" }}
              disabled={busy}
              title="Replace the damaged current version with the most recent healthy one"
              onClick={() => restoreServer(e.kind, e.damaged!.last_good_version_id!, e.key)}
            >
              {restoring ? <><span className="spinner" style={{ width: 12, height: 12, marginRight: 6 }} />Restoring…</> : "Restore last good"}
            </button>
          ) : (
            <span style={{ fontSize: 11, color: "var(--text-muted)" }} title="No healthy generation on the server">no good copy</span>
          )
        ) : e.source === "local-bak" ? (
          <button
            className="btn btn-ghost"
            style={{ fontSize: 12, padding: "3px 10px" }}
            disabled={busy}
            title="Restore this local backup to disk"
            onClick={() => restoreBak(e)}
          >
            {restoring ? <><span className="spinner" style={{ width: 12, height: 12, marginRight: 6 }} />Restoring…</> : "Restore backup"}
          </button>
        ) : (
          <button
            className="btn btn-ghost"
            style={{ fontSize: 12, padding: "3px 10px" }}
            disabled={e.isCurrent || busy || !e.versionId}
            title={e.isCurrent ? "This is the current version" : "Roll back to this version"}
            onClick={() => e.versionId && restoreServer(e.kind, e.versionId, e.key)}
          >
            {restoring ? <><span className="spinner" style={{ width: 12, height: 12, marginRight: 6 }} />Restoring…</> : "Restore"}
          </button>
        )}
      </li>
    );
  }

  const anyDamaged = integrity && (integrity.save.status === "damaged" || integrity.state.status === "damaged");

  const body = (
    <>
      {anyDamaged && (
        <p style={{ fontSize: 12, color: "var(--red)", margin: "4px 0 8px" }}>
          ⚠ This game's current {integrity!.save.status === "damaged" ? "save" : "state"} looks damaged. Restore the last good copy below.
        </p>
      )}
      {entries === null ? (
        <div style={{ textAlign: "center", padding: "16px 0" }}>
          <span className="spinner" style={{ width: 20, height: 20 }} />
        </div>
      ) : error && entries.length === 0 ? (
        <p style={{ color: "var(--red)" }}>{error}</p>
      ) : entries.length === 0 ? (
        <p style={{ color: "var(--text-muted)" }}>No save or state history yet for this game.</p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: "8px 0 0" }}>
          {entries.map(renderRow)}
        </ul>
      )}
      {status && <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 12 }}>{status}</p>}
    </>
  );

  if (embedded) return body;
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ width: 540 }} onClick={(e) => e.stopPropagation()}>
        <h3>Save &amp; state recovery — {name}</h3>
        {body}
        <div className="modal-actions">
          <button className="btn btn-ghost" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}
