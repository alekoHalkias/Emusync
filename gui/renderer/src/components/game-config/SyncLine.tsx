import React, { useEffect, useState } from "react";
import { RelTime } from "../../time";

export type SyncOp = { status: "idle" | "busy" | "ok" | "error"; action: "push" | "pull" | null; msg: string };
export const IDLE_OP: SyncOp = { status: "idle", action: null, msg: "" };

// Compact one-line sync row shown under a save/state location field (#264):
//   Sync: 💾 <local> · ☁ <server>            [↑ Push] [↓ Pull]
// The Push/Pull buttons flash ✓/✗ briefly on result instead of a status line.
export function SyncLine({
  localTime, serverTime, op, onPush, onPull, pushDisabled, pullDisabled,
}: {
  localTime: string | null;
  serverTime: string | null;
  op: SyncOp;
  onPush: () => void;
  onPull: () => void;
  pushDisabled: boolean;
  pullDisabled: boolean;
}): React.ReactElement {
  const busy = op.status === "busy";
  const [flash, setFlash] = useState<{ action: "push" | "pull"; ok: boolean } | null>(null);
  useEffect(() => {
    if ((op.status === "ok" || op.status === "error") && op.action) {
      setFlash({ action: op.action, ok: op.status === "ok" });
      const t = setTimeout(() => setFlash(null), 1800);
      return () => clearTimeout(t);
    }
  }, [op.status, op.action]);

  function Btn({ action, onClick, disabled, label }: {
    action: "push" | "pull"; onClick: () => void; disabled: boolean; label: string;
  }): React.ReactElement {
    const showSpinner = busy && op.action === action;
    const f = flash?.action === action ? flash : null;
    return (
      <button
        className="btn btn-ghost"
        style={{ fontSize: 12, padding: "3px 10px", minWidth: 64, color: f ? (f.ok ? "var(--green)" : "var(--red)") : undefined }}
        disabled={busy || disabled}
        onClick={onClick}
        title={op.action === action && op.status === "error" ? op.msg : undefined}
      >
        {showSpinner ? <span className="spinner" style={{ width: 10, height: 10 }} /> : f ? (f.ok ? "✓" : "✗") : label}
      </button>
    );
  }

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 6, fontSize: 13, flexWrap: "wrap" }}>
      <span style={{ color: "var(--text-muted)", fontSize: 12 }}>Sync:</span>
      <span title="On this device"><span style={{ opacity: 0.7 }}>💾</span> <RelTime iso={localTime} /></span>
      <span style={{ color: "var(--text-muted)" }}>·</span>
      <span title="On the server"><span style={{ opacity: 0.7 }}>☁️</span> <RelTime iso={serverTime} /></span>
      <span style={{ flex: 1 }} />
      <Btn action="push" onClick={onPush} disabled={pushDisabled} label="↑ Push" />
      <Btn action="pull" onClick={onPull} disabled={pullDisabled} label="↓ Pull" />
    </div>
  );
}
