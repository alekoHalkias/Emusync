// Theme import modal (#595): pick a .theme ZIP or a theme folder, send to the
// main process for validation and installation into <configDir>/themes/.
import { useState } from "react";
import type { ReactElement } from "react";
import { CloseIcon } from "./icons";
import Modal from "./Modal";

type State = "idle" | "importing" | "done" | "error";

export default function ThemeImportModal({ onClose, onImported }: { onClose: () => void; onImported: () => void }): ReactElement {
  const [state, setState] = useState<State>("idle");
  const [message, setMessage] = useState("");

  async function handleZipPick(): Promise<void> {
    const path = await window.emusync.dialog.openFile({
      title: "Import Theme",
      filters: [{ name: "Theme", extensions: ["theme", "zip"] }],
    });
    if (!path) return;
    await importPath(path);
  }

  async function handleFolderPick(): Promise<void> {
    const path = await window.emusync.dialog.openFolder();
    if (!path) return;
    await importPath(path);
  }

  async function importPath(path: string): Promise<void> {
    setState("importing");
    setMessage("Importing theme...");
    try {
      const id = await window.emusync.theme.import(path);
      setMessage(`Theme "${id}" installed.`);
      setState("done");
      onImported();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setMessage(msg);
      setState("error");
    }
  }

  return (
    <Modal size="md" onClose={onClose}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <h3 style={{ margin: 0 }}>Import Theme</h3>
        <button className="btn btn-ghost" aria-label="Close" onClick={onClose}><CloseIcon /></button>
      </div>

      {state === "idle" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <button
            className="btn btn-ghost"
            style={{ textAlign: "left", padding: "14px 16px" }}
            onClick={handleZipPick}
          >
            <div style={{ fontWeight: 600, marginBottom: 4 }}>Import .theme ZIP</div>
            <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
              Select a .theme or .zip file containing a theme.json manifest.
            </div>
          </button>
          <button
            className="btn btn-ghost"
            style={{ textAlign: "left", padding: "14px 16px" }}
            onClick={handleFolderPick}
          >
            <div style={{ fontWeight: 600, marginBottom: 4 }}>Import Theme Folder</div>
            <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
              Select a folder with theme.json and optional assets.
            </div>
          </button>
        </div>
      )}

      {state === "importing" && (
        <div style={{ textAlign: "center", padding: "20px 0" }}>
          <span className="spinner" style={{ width: 28, height: 28, display: "inline-block" }} />
          <p style={{ marginTop: 12 }}>{message}</p>
        </div>
      )}

      {state === "done" && (
        <div style={{ textAlign: "center", padding: "10px 0" }}>
          <p>{message}</p>
        </div>
      )}

      {state === "error" && (
        <div style={{ padding: "10px 0" }}>
          <p style={{ color: "var(--danger)", margin: 0 }}>{message}</p>
        </div>
      )}

      <div className="modal-actions">
        <button className="btn btn-ghost" onClick={onClose}>Close</button>
      </div>
    </Modal>
  );
}
