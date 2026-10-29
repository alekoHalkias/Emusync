import React, { useEffect, useState } from "react";
import { getDeviceConsoles, getGame, whoami } from "../../api";

const norm = (p: string): string => p.replace(/\\/g, "/").replace(/\/+$/, "");

// Local ROM outside its console's default local folder (#622): offer to move
// it in. Network-sourced ROMs are handled by NetworkRomPanel.
export function MoveLocalRomPanel({
  slug, romSource, romPath, onMoved,
}: {
  slug: string | null;
  romSource: string;
  romPath: string;
  onMoved: (romPath: string, launchCommand?: string) => void;
}): React.ReactElement | null {
  const [folder, setFolder] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    if (!slug || romSource === "network") { setFolder(""); return; }
    (async () => {
      try {
        const game = await getGame(slug);
        const { device_id } = await whoami();
        const matches = (await getDeviceConsoles(device_id)).filter(c => c.console_name === game.console);
        setFolder(matches.find(c => c.device_local_folder)?.device_local_folder || "");
      } catch { setFolder(""); }
    })();
  }, [slug, romSource]);

  if (!slug || romSource === "network" || !folder || !romPath) return null;
  if (norm(romPath).startsWith(norm(folder) + "/")) return null;

  async function handleMove(): Promise<void> {
    setBusy(true); setMsg("Moving…");
    // Cross-disk moves copy the file; show progress so it doesn't look stuck.
    const l = window.emusync.rom.onLocalizeProgress(p => {
      if (p.slug === slug && p.total > 0) setMsg(`Copying ${Math.round((p.copied / p.total) * 100)}%`);
    });
    try {
      const r = await window.emusync.rom.moveToConsoleFolder(slug!);
      if (r.ok) { onMoved(r.romPath ?? "", r.launchCommand); setMsg("Moved."); }
      else setMsg(r.error ?? "Move failed.");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Move failed.");
    } finally {
      window.emusync.rom.offLocalizeProgress(l);
      setBusy(false);
    }
  }

  return (
    <div style={{ marginTop: 8, padding: "8px 10px", background: "var(--bg-subtle, rgba(127,127,127,0.08))", borderRadius: 6 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <button className="btn" disabled={busy} onClick={handleMove} style={{ flexShrink: 0 }} title={`Moves the ROM to ${folder}`}>Move to console folder</button>
        {(busy || msg) && <span style={{ fontSize: 13, color: "var(--text-muted)" }}>{msg}</span>}
      </div>
    </div>
  );
}
