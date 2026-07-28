// Per-game "Folder" tab for Switch games (#441): since Switch games live
// one-per-folder and sync as a whole folder via emusync push/pull, this is
// the local-file counterpart — see what's in the folder, reveal it in the OS
// file manager, and add a file (e.g. a DLC .nsp) straight from the GUI.
import React, { useEffect, useState } from "react";

export default function GameFolderTab({ slug }: { slug: string }): React.ReactElement {
  const [folder, setFolder] = useState<string | null>(null);
  const [files, setFiles] = useState<{ name: string; sizeBytes: number }[] | null>(null);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");

  async function refresh(): Promise<void> {
    const result = await window.emusync.gameFolder.list(slug);
    setFolder(result?.folder ?? null);
    setFiles(result?.files ?? []);
  }

  useEffect(() => { refresh(); }, [slug]);

  async function handleReveal(): Promise<void> {
    const result = await window.emusync.gameFolder.reveal(slug);
    if (!result.ok) setError(result.error || "Failed to open folder");
  }

  async function handleAdd(): Promise<void> {
    setError("");
    const picked = await window.emusync.dialog.openFile({
      title: "Select a file to add to this game's folder",
      filters: [{ name: "Switch update/DLC", extensions: ["nsp", "xci"] }],
    });
    if (!picked) return;
    setAdding(true);
    const result = await window.emusync.gameFolder.addFile(slug, picked);
    setAdding(false);
    if (!result.ok) { setError(result.error || "Failed to add file"); return; }
    await refresh();
  }

  return (
    <div>
      <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 12 }}>
        This game's whole folder syncs as one unit when you push/pull it to another
        device — any update or DLC file placed here rides along automatically.
        Eden has no automatic install for updates/DLC, so install them there via
        Eden's own <strong>File &gt; Install Files to NAND...</strong> after they arrive.
      </p>

      {folder && (
        <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12, fontFamily: "monospace", wordBreak: "break-all" }}>
          {folder}
        </p>
      )}

      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <button className="btn btn-ghost" onClick={handleReveal} disabled={!folder}>
          Open folder
        </button>
        <button className="btn btn-primary" onClick={handleAdd} disabled={adding || !folder}>
          {adding ? "Adding..." : "Add file..."}
        </button>
      </div>

      {error && <p style={{ color: "var(--red, #e05555)", fontSize: 13 }}>{error}</p>}

      {files === null && <p>Loading...</p>}
      {files !== null && files.length === 0 && (
        <p style={{ color: "var(--text-muted)" }}>No files found.</p>
      )}
      {files !== null && files.length > 0 && (
        <ul style={{ listStyle: "none", padding: 0 }}>
          {files.map((f) => (
            <li key={f.name} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
              <span style={{ flex: 1 }}>{f.name}</span>
              <span style={{ color: "var(--text-muted)", fontSize: 12 }}>
                {(f.sizeBytes / (1024 * 1024)).toFixed(1)} MB
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
