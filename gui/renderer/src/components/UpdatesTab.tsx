// Per-game "Updates" tab for Switch games (#441): Eden has no headless
// install path for update/DLC .nsp files and its installed content lives in
// one shared NAND content store, not a per-title folder, so it can't be
// synced like a save/state. Instead this manages the not-yet-installed files
// themselves — added into a managed per-game folder and pushed to other
// devices, which still do the one remaining manual "Install Files to NAND"
// step in Eden themselves.
import React, { useEffect, useState } from "react";
import { useDevices } from "../DeviceContext";

type UpdateFile = { name: string; sizeBytes: number };
type PushState = { status: "idle" | "loading" | "success" | "error"; message?: string };

export default function UpdatesTab({ slug }: { slug: string }): React.ReactElement {
  const { devices: allDevices, currentDeviceId } = useDevices();
  const [files, setFiles] = useState<UpdateFile[] | null>(null);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");
  const [pushTarget, setPushTarget] = useState<Record<string, string>>({});
  const [pushState, setPushState] = useState<Record<string, PushState>>({});

  async function refresh(): Promise<void> {
    try {
      setFiles(await window.emusync.update.list(slug));
    } catch {
      setFiles([]);
    }
  }

  useEffect(() => { refresh(); }, [slug]);

  async function handleAdd(): Promise<void> {
    setError("");
    const picked = await window.emusync.dialog.openFile({
      title: "Select an update or DLC file",
      filters: [{ name: "Switch update/DLC", extensions: ["nsp", "xci"] }],
    });
    if (!picked) return;
    setAdding(true);
    const result = await window.emusync.update.add(slug, picked);
    setAdding(false);
    if (!result.ok) { setError(result.error || "Failed to add file"); return; }
    await refresh();
  }

  async function handlePush(filename: string): Promise<void> {
    const toDeviceId = pushTarget[filename];
    if (!toDeviceId) return;
    setPushState(prev => ({ ...prev, [filename]: { status: "loading" } }));
    const result = await window.emusync.update.push(slug, filename, toDeviceId);
    const targetName = allDevices.find(d => d.id === toDeviceId)?.name || "the device";
    setPushState(prev => ({
      ...prev,
      [filename]: result.ok
        ? { status: "success", message: result.targetOnline ? `Sent to ${targetName}` : `Queued — will deliver when ${targetName} comes online` }
        : { status: "error", message: result.error || "Push failed" },
    }));
  }

  const otherDevices = allDevices.filter(d => d.id !== currentDeviceId);

  return (
    <div>
      <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 12 }}>
        Manage update/DLC files for this game. Eden has no way to install these
        automatically — after a file lands on a device, install it there via
        Eden's own <strong>File &gt; Install Files to NAND...</strong>.
      </p>

      <button className="btn btn-primary" onClick={handleAdd} disabled={adding} style={{ marginBottom: 16 }}>
        {adding ? "Adding..." : "Add update/DLC file..."}
      </button>

      {error && <p style={{ color: "var(--red, #e05555)", fontSize: 13 }}>{error}</p>}

      {files === null && <p>Loading...</p>}
      {files !== null && files.length === 0 && (
        <p style={{ color: "var(--text-muted)" }}>No update/DLC files managed for this game yet.</p>
      )}

      {files !== null && files.length > 0 && (
        <ul style={{ listStyle: "none", padding: 0 }}>
          {files.map((f) => {
            const state = pushState[f.name];
            return (
              <li key={f.name} style={{ padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ flex: 1 }}>{f.name}</span>
                  <span style={{ color: "var(--text-muted)", fontSize: 12 }}>
                    {(f.sizeBytes / (1024 * 1024)).toFixed(1)} MB
                  </span>
                </div>
                {otherDevices.length > 0 && (
                  <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
                    <select
                      value={pushTarget[f.name] || ""}
                      onChange={(e) => setPushTarget(prev => ({ ...prev, [f.name]: e.target.value }))}
                      style={{ flex: 1 }}
                    >
                      <option value="">Push to device...</option>
                      {otherDevices.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
                    </select>
                    <button
                      className="btn btn-ghost"
                      disabled={!pushTarget[f.name] || state?.status === "loading"}
                      onClick={() => handlePush(f.name)}
                    >
                      {state?.status === "loading" ? "Pushing..." : "Push"}
                    </button>
                  </div>
                )}
                {state && state.status !== "loading" && (
                  <p style={{ fontSize: 12, marginTop: 4, color: state.status === "error" ? "var(--red, #e05555)" : "var(--text-muted)" }}>
                    {state.message}
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
