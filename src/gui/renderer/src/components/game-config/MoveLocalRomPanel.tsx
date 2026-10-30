import React, { useEffect, useState } from "react";
import { getDeviceConsoles, getGame, whoami } from "../../api";
import { norm, uploadLocalRom } from "./localToNetwork";

// Local ROM actions: move a ROM outside its console's default local folder
// into it (#622), and upload it to the console's network folder (#624).
// Network-sourced ROMs are handled by NetworkRomPanel.
export function MoveLocalRomPanel({
  slug, romSource, romPath, onMoved, onUploaded,
}: {
  slug: string | null;
  romSource: string;
  romPath: string;
  onMoved: (romPath: string, launchCommand?: string) => void;
  onUploaded: (masterPath: string, localPath: string, launchCommand: string, relPath: string, sha256: string) => void;
}): React.ReactElement | null {
  const [folder, setFolder] = useState("");
  const [netFolder, setNetFolder] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    if (!slug || romSource === "network") { setFolder(""); setNetFolder(""); return; }
    (async () => {
      try {
        const game = await getGame(slug);
        const { device_id } = await whoami();
        const matches = (await getDeviceConsoles(device_id)).filter(c => c.console_name === game.console);
        setFolder(matches.find(c => c.device_local_folder)?.device_local_folder || "");
        setNetFolder(matches.find(c => c.device_network_folder)?.device_network_folder || "");
      } catch { setFolder(""); setNetFolder(""); }
    })();
  }, [slug, romSource]);

  if (!slug || romSource === "network" || !romPath) return null;
  const canMove = !!folder && !norm(romPath).startsWith(norm(folder) + "/");
  if (!canMove && !netFolder) return null;

  async function handleMove(): Promise<void> {
    setBusy(true); setMsg("Moving…");
    // Cross-disk moves copy the file; show progress so it doesn't look stuck.
    const l = window.emusync.rom.onLocalizeProgress(p => {
      if (p.slug === slug && p.total > 0) setMsg(`Copying ${Math.round((p.copied / p.total) * 100)}%`);
    });
    try {
      const r = await window.emusync.rom.moveToConsoleFolder(slug!);
      if (r.ok) { onMoved(r.romPath ?? "", r.launchCommand); setMsg(r.adopted ? "Game re-pathed to the existing file in the console folder." : "Moved."); }
      else setMsg(r.error ?? "Move failed.");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Move failed.");
    } finally {
      window.emusync.rom.offLocalizeProgress(l);
      setBusy(false);
    }
  }

  // Copy the ROM up to the network folder and flip the game to network-sourced,
  // keeping this device's file as the local copy (mirrors the import wizard).
  async function handleUpload(): Promise<void> {
    setBusy(true); setMsg("Uploading…");
    try {
      const r = await uploadLocalRom(slug!, romPath, folder, netFolder);
      if (!r.ok) { setMsg(r.error); return; }
      onUploaded(r.master, romPath, r.launch, r.rel, r.sha);
      setMsg(r.skipped ? "Already on the network drive; linked." : "Added to the network drive.");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Upload failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ marginTop: 8, padding: "8px 10px", background: "var(--bg-subtle, rgba(127,127,127,0.08))", borderRadius: 6 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        {canMove && <button className="btn" disabled={busy} onClick={handleMove} style={{ flexShrink: 0 }} title={`Moves the ROM to ${folder}`}>Move to console folder</button>}
        {netFolder && <button className="btn" disabled={busy} onClick={handleUpload} style={{ flexShrink: 0 }} title={`Copies the ROM to ${netFolder}`}>Add to network drive</button>}
        {(busy || msg) && <span style={{ fontSize: 13, color: "var(--text-muted)" }}>{msg}</span>}
      </div>
    </div>
  );
}
