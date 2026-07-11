// Byte-level progress modal for the bulk ROM download (issue #396):
// "Downloading game n of N" / current game name / overall progress bar /
// bytes done of total + speed / Cancel. Purely presentational — GameGrid
// owns the download loop, progress subscription, and cancellation.
import React from "react";

export type DownloadModalState = {
  index: number;        // 1-based game currently downloading
  count: number;        // total games in this batch
  gameName: string;
  doneBytes: number;    // completed games + current game's copied bytes
  totalBytes: number;   // whole batch
  speedBps: number;     // bytes/second, 0 until the first measurement
};

function fmtBytes(n: number): string {
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(2)} GB`;
  if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  if (n >= 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${n} B`;
}

type Props = {
  state: DownloadModalState;
  cancelling: boolean;
  onCancel: () => void;
};

export default function DownloadProgressModal({ state, cancelling, onCancel }: Props): React.ReactElement {
  const pct = state.totalBytes > 0 ? Math.min(100, (state.doneBytes / state.totalBytes) * 100) : 0;
  return (
    <div className="modal-overlay">
      <div className="modal">
        <h3>Downloading game {state.index} of {state.count}</h3>
        <p style={{ marginBottom: 12 }}>Downloading {state.gameName}</p>
        <div className="download-progress-track">
          <div className="download-progress-fill" style={{ width: `${pct}%` }} />
        </div>
        <p style={{ fontSize: 13, marginTop: 8, marginBottom: 20 }}>
          {fmtBytes(state.doneBytes)} / {fmtBytes(state.totalBytes)}
          {state.speedBps > 0 && <> • {fmtBytes(state.speedBps)}/s</>}
        </p>
        <div className="modal-actions">
          <button className="btn btn-ghost" onClick={onCancel} disabled={cancelling}>
            {cancelling ? <><span className="spinner" /> Cancelling…</> : "Cancel"}
          </button>
        </div>
      </div>
    </div>
  );
}
