import React from "react";
import { RelTime } from "../time";
import Modal from "./Modal";
import { WarningIcon } from "./icons";

/** Props for the side-by-side conflict resolution modal (issue #579). */
type Props = {
  gameName: string;
  kind: "save" | "state";
  localHash: string;
  serverHash: string;
  serverPushedAt: string;
  onChoose: (winner: "local" | "server") => void;
  onClose: () => void;
};

function fmtHash(h: string): string {
  return h.slice(0, 12) + "..." + h.slice(-8);
}

/**
 * Conflict-resolution modal shown when manual push/pull detects a divergence
 * (both local and server moved past the sync baseline). Presents a side-by-side
 * comparison so the user can choose which version to keep.
 */
export default function SyncConflictModal({
  gameName, kind, localHash, serverHash, serverPushedAt, onChoose, onClose,
}: Props): React.ReactElement {
  return (
    <Modal size="md" onClose={onClose}>
      <h3 style={{ marginBottom: 4 }}>
        <WarningIcon style={{ marginRight: 8, verticalAlign: "middle" }} />
        Conflict: {gameName}
      </h3>
      <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 0 }}>
        Both versions of this {kind} changed since the last sync. Choose which to keep:
      </p>

      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, margin: "8px 0" }}>
        <thead>
          <tr style={{ borderBottom: "2px solid var(--border)" }}>
            <th style={{ textAlign: "left", padding: "6px 12px", fontWeight: 500 }}>Local</th>
            <th style={{ textAlign: "left", padding: "6px 12px", fontWeight: 500 }}>Server</th>
          </tr>
        </thead>
        <tbody>
          <tr style={{ borderBottom: "1px solid var(--border)" }}>
            <td style={{ padding: "6px 12px" }}>
              <code style={{ fontSize: 11 }}>{fmtHash(localHash)}</code>
            </td>
            <td style={{ padding: "6px 12px" }}>
              <code style={{ fontSize: 11 }}>{fmtHash(serverHash)}</code>
            </td>
          </tr>
          <tr style={{ borderBottom: "1px solid var(--border)" }}>
            <td style={{ padding: "6px 12px", color: "var(--text-muted)" }}>
              (this device)
            </td>
            <td style={{ padding: "6px 12px", color: "var(--text-muted)" }}>
              <RelTime iso={serverPushedAt} />
            </td>
          </tr>
        </tbody>
      </table>

      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <button
          className="btn"
          style={{ flex: 1 }}
          onClick={() => onChoose("local")}
        >
          Keep Local
        </button>
        <button
          className="btn btn-ghost"
          style={{ flex: 1 }}
          onClick={() => onChoose("server")}
        >
          Use Server
        </button>
      </div>

      <div className="modal-actions">
        <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
      </div>
    </Modal>
  );
}
