import React, { useEffect, useState } from "react";
import { getDeviceConsoles, getGame, whoami } from "../../api";

// Network-ROM (issue #255) localize/delocalize UI — copy a network-sourced
// ROM onto local disk for offline play, or remove the local copy. The NAS
// master is never touched. `localRomPath` is lifted to the parent since
// GameConfig's save flow needs the current local copy path for its rename
// logic; everything else here is self-contained.
export function NetworkRomPanel({
  slug, romSource, localRomPath, onLocalRomPathChange,
}: {
  slug: string | null;
  romSource: string;
  localRomPath: string;
  onLocalRomPathChange: (path: string) => void;
}): React.ReactElement | null {
  const [localDestFolder, setLocalDestFolder] = useState("");  // console's configured local-copy folder
  const [romBusy, setRomBusy] = useState(false);
  const [romMsg, setRomMsg] = useState("");

  // Resolve the console's configured local-copy destination for a network ROM,
  // so we can show it and localize without re-prompting (issue #255).
  useEffect(() => {
    if (!slug || romSource !== "network") { setLocalDestFolder(""); return; }
    (async () => {
      try {
        const game = await getGame(slug);
        const { device_id } = await whoami();
        const consoles = await getDeviceConsoles(device_id);
        const matches = consoles.filter(c => c.console_name === game.console);
        setLocalDestFolder(matches.find(c => c.device_local_folder)?.device_local_folder
          || matches[0]?.device_local_folder || "");
      } catch { setLocalDestFolder(""); }
    })();
  }, [slug, romSource]);

  if (romSource !== "network") return null;

  // Copy this network ROM onto local disk for offline play.
  async function handleLocalize(): Promise<void> {
    if (!slug) return;
    setRomBusy(true); setRomMsg("");
    // Use the console's configured destination if we have one; otherwise ask once.
    let folder = localDestFolder;
    if (!folder) {
      const picked = await window.emusync.dialog.openFolder();
      if (!picked) { setRomBusy(false); return; }
      folder = picked;
      setLocalDestFolder(picked);   // remember it locally; the copy teaches the console
    }
    const r = await window.emusync.rom.localize(slug, folder);
    if (r.ok) { onLocalRomPathChange(r.localPath ?? ""); setRomMsg("✓ Localized for offline play."); }
    else setRomMsg(r.error ?? "Localize failed.");
    setRomBusy(false);
  }

  async function handlePickDestFolder(): Promise<void> {
    const picked = await window.emusync.dialog.openFolder();
    if (picked) { setLocalDestFolder(picked); setRomMsg("Destination set — it'll be used on the next copy."); }
  }

  async function handleDelocalize(): Promise<void> {
    if (!slug) return;
    setRomBusy(true); setRomMsg("");
    const r = await window.emusync.rom.delocalize(slug);
    if (r.ok) { onLocalRomPathChange(""); setRomMsg("✓ Local copy removed."); }
    else setRomMsg(r.error ?? "Failed to remove local copy.");
    setRomBusy(false);
  }

  return (
    <div style={{ marginTop: 8, padding: "8px 10px", background: "var(--bg-subtle, rgba(127,127,127,0.08))", borderRadius: 6 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ fontSize: 13, minWidth: 0 }}>🌐 Network ROM</span>
        {localRomPath ? (
          <button className="btn" disabled={romBusy} onClick={handleDelocalize} style={{ flexShrink: 0 }}>Remove offline copy</button>
        ) : (
          <>
            <button className="btn" disabled={romBusy} onClick={handleLocalize} style={{ flexShrink: 0 }}>Copy for offline play</button>
            <button
              className="btn btn-ghost"
              style={{ flexShrink: 0 }}
              onClick={handlePickDestFolder}
              title={localDestFolder ? `Local copies go to: ${localDestFolder}` : "Choose where local copies are saved"}
            >
              {localDestFolder ? "Change folder…" : "Choose folder…"}
            </button>
          </>
        )}
        {romBusy && <span style={{ fontSize: 13, color: "var(--text-muted)", flexShrink: 0 }}>Working…</span>}
        {!romBusy && romMsg && <span style={{ fontSize: 13, color: "var(--text-muted)", flexShrink: 0 }}>{romMsg}</span>}
      </div>
    </div>
  );
}
