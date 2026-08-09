// Entry point for the import modal (#462): offers "Add console" (the
// existing single-console wizard, unchanged) or "Import library" (bulk
// folder-per-console import) before handing off to either one.
import { useState } from "react";
import type { ReactElement } from "react";
import ConsoleImport from "./ConsoleImport";
import LibraryImport from "./LibraryImport";

type Mode = "choice" | "console" | "library";
type Props = { onClose: () => void; onImported: () => void };

export default function ImportWizard({ onClose, onImported }: Props): ReactElement {
  const [mode, setMode] = useState<Mode>("choice");

  if (mode === "console") return <ConsoleImport onClose={onClose} onImported={onImported} />;
  if (mode === "library") return <LibraryImport onClose={onClose} onImported={onImported} />;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ width: "clamp(480px, 60vw, 640px)" }} onClick={e => e.stopPropagation()}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <h3 style={{ margin: 0 }}>Add games</h3>
          <button className="btn btn-ghost" onClick={onClose}>✕</button>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <button
            className="btn btn-ghost"
            style={{ textAlign: "left", padding: "14px 16px" }}
            onClick={() => setMode("console")}
          >
            <div style={{ fontWeight: 600, marginBottom: 4 }}>Add console</div>
            <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
              Pick one console, then an emulator, then the ROMs to import.
            </div>
          </button>
          <button
            className="btn btn-ghost"
            style={{ textAlign: "left", padding: "14px 16px" }}
            onClick={() => setMode("library")}
          >
            <div style={{ fontWeight: 600, marginBottom: 4 }}>Import library</div>
            <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
              Point at a folder with one subfolder per console — scans, matches each
              folder to a console, and imports them one by one.
            </div>
          </button>
        </div>

        <div className="modal-actions">
          <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  );
}
