import React, { useEffect, useState } from "react";
import {
  createPullRequest,
  getDeviceConsoles,
  getGame,
  getGameNetworkSource,
  listGameDevices,
  whoami,
  type DeviceForGame,
  type GameNetworkSource,
} from "../api";

type Props = {
  slug: string;
  name: string;
  onClose: () => void;
  /** Called after a successful network-drive setup so the parent can launch. */
  onPlay: (slug: string, name: string) => void;
  /** Called after any change (setup / pull request) to refresh the game list. */
  onChanged: () => void;
};

function basename(p: string): string {
  return p.replace(/\\/g, "/").split("/").filter(Boolean).pop() || p;
}

/**
 * Play-time setup for a game that isn't configured on this device (issue #270).
 * Offers two ways to make it playable here:
 *   A. Point this device at the same network share (its own mount root) and play.
 *   B. Pull the ROM bytes from a device that has it (delivered by sync-daemon).
 */
export default function NetworkPlaySetup({ slug, name, onClose, onPlay, onChanged }: Props): React.ReactElement {
  const [netSource, setNetSource] = useState<GameNetworkSource | null>(null);
  const [sources, setSources] = useState<DeviceForGame[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<"" | "network" | "pull">("");
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    Promise.allSettled([getGameNetworkSource(slug), listGameDevices(slug)])
      .then(([ns, devs]) => {
        if (ns.status === "fulfilled") setNetSource(ns.value);
        if (devs.status === "fulfilled") setSources(devs.value.filter(d => d.rom_path));
      })
      .finally(() => setLoading(false));
  }, [slug]);

  async function useNetworkDrive(): Promise<void> {
    setError(null); setStatus(null);
    const mount = await window.emusync.dialog.openFolder();
    if (!mount) return;
    setBusy("network");
    try {
      const res = await window.emusync.rom.setupNetworkPlay(slug, mount);
      if (!res.ok) { setError(res.error || "Setup failed"); return; }
      onChanged();
      onClose();
      onPlay(slug, name);
    } finally {
      setBusy("");
    }
  }

  async function pullToDevice(): Promise<void> {
    setError(null); setStatus(null);
    setBusy("pull");
    try {
      const source = sources[0];
      if (!source?.rom_path) { setError("No device has this ROM to pull from."); return; }

      // Destination: this device's configured ROM folder for the game's console,
      // else ask the user to pick one.
      const game = await getGame(slug);
      let folder = "";
      try {
        const { device_id } = await whoami();
        const consoles = await getDeviceConsoles(device_id);
        folder = consoles.find(c => c.console_name === game.console)?.device_game_folder || "";
      } catch { /* fall through to picker */ }
      if (!folder) {
        const picked = await window.emusync.dialog.openFolder();
        if (!picked) { setBusy(""); return; }
        folder = picked;
      }

      const destination = `${folder.replace(/[/\\]$/, "")}/${basename(source.rom_path)}`;
      const res = await createPullRequest(slug, source.id, destination);
      setStatus(
        res.source_online
          ? `Requested from ${source.name}. It will arrive shortly (keep both devices' EmuSync running).`
          : `${source.name} is offline — the ROM will be delivered when it comes online.`,
      );
      onChanged();
    } catch (e: any) {
      setError(e.message || "Pull request failed");
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ width: 520 }} onClick={(e) => e.stopPropagation()}>
        <h3>Play “{name}” on this device</h3>
        {loading ? (
          <div style={{ textAlign: "center", padding: "16px 0" }}>
            <span className="spinner" style={{ width: 20, height: 20 }} />
          </div>
        ) : (
          <>
            <p style={{ fontSize: 13, color: "var(--text-muted)" }}>
              This game isn’t set up on this device yet. Choose how to make it playable here:
            </p>

            {/* Option A — network drive */}
            <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 12, marginTop: 8 }}>
              <div style={{ fontWeight: 500, fontSize: 14 }}>🌐 Use the network drive</div>
              <div style={{ fontSize: 12, color: "var(--text-muted)", margin: "4px 0 8px" }}>
                {netSource
                  ? <>Configured on <b>{netSource.device_name}</b> as <code>{netSource.rom_rel_path}</code>. Point this device at the same share to play from it.</>
                  : "No device has this game on a network share."}
              </div>
              <button
                className="btn"
                disabled={!netSource || busy !== ""}
                onClick={useNetworkDrive}
              >
                {busy === "network" ? <><span className="spinner" style={{ width: 12, height: 12, marginRight: 6 }} />Verifying…</> : "Choose mount root & play"}
              </button>
            </div>

            {/* Option B — pull to this device */}
            <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 12, marginTop: 8 }}>
              <div style={{ fontWeight: 500, fontSize: 14 }}>💾 Pull the ROM to this device</div>
              <div style={{ fontSize: 12, color: "var(--text-muted)", margin: "4px 0 8px" }}>
                {sources.length
                  ? <>Copy the ROM from <b>{sources[0].name}</b> onto this device for offline play.</>
                  : "No device currently has this ROM to pull from."}
              </div>
              <button
                className="btn btn-ghost"
                disabled={sources.length === 0 || busy !== ""}
                onClick={pullToDevice}
              >
                {busy === "pull" ? <><span className="spinner" style={{ width: 12, height: 12, marginRight: 6 }} />Requesting…</> : "Pull ROM here"}
              </button>
            </div>

            {error && <p style={{ color: "var(--red)", fontSize: 12, marginTop: 12 }}>{error}</p>}
            {status && <p style={{ color: "var(--text-muted)", fontSize: 12, marginTop: 12 }}>{status}</p>}
          </>
        )}
        <div className="modal-actions">
          <button className="btn btn-ghost" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}
