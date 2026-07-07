import type { ConsoleImportVM } from "./useConsoleImport";

export function DoneStep({ vm }: { vm: ConsoleImportVM }) {
  const { progress, importErrors, pushResults, artProgress } = vm;
  const fetchingArt = artProgress.total > 0 && artProgress.done < artProgress.total;
  return (
    <>
      <div style={{ padding: "24px 0 12px", textAlign: "center" }}>
        <div style={{ fontSize: 36, marginBottom: 8 }}>✓</div>
        <p style={{ fontWeight: 600 }}>
          {progress.total - importErrors.length} of {progress.total} games imported
        </p>
        {importErrors.length > 0 && (
          <p style={{ fontSize: 12, color: "var(--text-muted)" }}>
            Failed: {importErrors.join(", ")}
          </p>
        )}
        {fetchingArt && (
          <p style={{ fontSize: 12, color: "var(--text-muted)", display: "flex", alignItems: "center", justifyContent: "center", gap: 6, marginTop: 6 }}>
            <span className="spinner" style={{ width: 12, height: 12, flexShrink: 0 }} />
            Fetching artwork… {artProgress.done}/{artProgress.total}
          </p>
        )}
      </div>

      {pushResults.length > 0 && (
        <div style={{ borderTop: "1px solid var(--border)", paddingTop: 12, marginBottom: 8 }}>
          <p style={{ fontSize: 12, fontWeight: 500, marginBottom: 8, color: "var(--text-muted)" }}>
            Syncing to other devices
          </p>
          {pushResults.map(r => (
            <div key={r.deviceName} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, marginBottom: 6 }}>
              {r.status === "pushing" && <span className="spinner" style={{ width: 12, height: 12, flexShrink: 0 }} />}
              {r.status === "ok"      && <span className="ci-ok">✓</span>}
              {r.status === "offline" && <span>📤</span>}
              {r.status === "error"   && <span style={{ color: "var(--red, #f44336)" }}>✗</span>}
              <span>
                {r.deviceName}
                {r.status === "pushing" && <span style={{ color: "var(--text-muted)" }}> — sending…</span>}
                {r.status === "offline" && <span style={{ color: "var(--text-muted)" }}> — queued, will sync when online</span>}
                {r.status === "error"   && <span style={{ color: "var(--text-muted)" }}> — {r.error}</span>}
              </span>
            </div>
          ))}
        </div>
      )}

      <div className="modal-actions">
        <button className="btn btn-primary" onClick={() => { vm.onImported(); vm.onClose(); }}>
          Done
        </button>
      </div>
    </>
  );
}
