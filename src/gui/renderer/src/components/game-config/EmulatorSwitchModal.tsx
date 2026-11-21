// Confirm an emulator switch (#753): save-compatibility warning, the new
// emulator's save/state paths, and whether to move existing saves there.
import React from "react";
import Modal from "../Modal";

type Props = {
  fromLabel: string;          // "" when the old command was Custom
  toLabel: string;
  savePath?: string;          // set only when the path changes
  statePath?: string;
  note?: string;              // e.g. "Applies to 4 games on this device."
  busy?: boolean;
  onCancel: () => void;
  onConfirm: (move: boolean) => void;
};

const pathStyle: React.CSSProperties = { fontFamily: "monospace", fontSize: 12, color: "var(--text-muted)", overflowWrap: "anywhere" };

export default function EmulatorSwitchModal({ fromLabel, toLabel, savePath, statePath, note, busy, onCancel, onConfirm }: Props): React.ReactElement {
  const changes = savePath !== undefined || statePath !== undefined;
  return (
    <Modal size="md" busy={busy} onClose={onCancel}>
      <h3>Switch to {toLabel}?</h3>
      <p style={{ fontSize: 13 }}>
        A save made with {fromLabel || "the previous emulator"} may not load in {toLabel}.
      </p>
      {note && <p style={{ fontSize: 13 }}>{note}</p>}
      {changes && (
        <>
          <p style={{ fontSize: 13 }}>{toLabel} uses a different location:</p>
          {savePath !== undefined && <div style={pathStyle}>Save: {savePath || "(learned after first play)"}</div>}
          {statePath !== undefined && <div style={pathStyle}>States: {statePath || "(none)"}</div>}
          <p style={{ fontSize: 13, marginTop: 8 }}>Move existing save files there? Files already at the new location are never overwritten.</p>
        </>
      )}
      <div className="modal-actions">
        <button className="btn btn-ghost" disabled={busy} onClick={onCancel}>Cancel</button>
        {changes ? (
          <>
            <button className="btn btn-ghost" disabled={busy} onClick={() => onConfirm(false)}>Keep files</button>
            <button className="btn btn-primary" disabled={busy} onClick={() => onConfirm(true)}>
              {busy ? <span className="spinner" /> : "Move saves"}
            </button>
          </>
        ) : (
          <button className="btn btn-primary" disabled={busy} onClick={() => onConfirm(false)}>
            {busy ? <span className="spinner" /> : "Switch"}
          </button>
        )}
      </div>
    </Modal>
  );
}
