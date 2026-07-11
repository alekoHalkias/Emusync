// "Steam is open — restart it?" confirmation (issue #393), shared by
// GameConfig's single add and GameGrid's bulk add. Purely presentational;
// the caller owns the shutdown → add → relaunch orchestration.
import React from "react";

type Props = {
  count: number;         // how many games the pending add covers (for the label)
  busy: boolean;         // true while shutdown/add/relaunch is in flight
  onYes: () => void;
  onNo: () => void;
};

export default function SteamRestartModal({ count, busy, onYes, onNo }: Props): React.ReactElement {
  return (
    <div className="modal-overlay" onClick={() => !busy && onNo()}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>Steam is open</h3>
        <p>
          Steam must be closed while shortcuts are added. Restart it to add
          {count === 1 ? " the game" : ` the ${count} games`}? Steam will close,
          the game{count === 1 ? "" : "s"} will be added, and Steam will reopen.
        </p>
        <div className="modal-actions">
          <button className="btn btn-ghost" onClick={onNo} disabled={busy}>No</button>
          <button className="btn btn-primary" onClick={onYes} disabled={busy}>
            {busy ? <><span className="spinner" /> Restarting Steam…</> : "Yes, restart Steam"}
          </button>
        </div>
      </div>
    </div>
  );
}
