import React, { useEffect, useState } from "react";
import {
  listGameDevices,
  getDeviceGameDevices,
  getDeviceConsoles,
  createPullRequest,
  type Device,
} from "../../api";
import { useDevices } from "../../DeviceContext";
import type { DeviceModalTarget, TransferState } from "./types";

type Props = DeviceModalTarget & { onClose: () => void };

/** Returns a freshness tier based on last_seen_at ISO string. */
function deviceFreshness(lastSeenAt: string | null | undefined): "online" | "recent" | "stale" {
  if (!lastSeenAt) return "stale";
  const ageMs = Date.now() - new Date(lastSeenAt).getTime();
  if (ageMs < 5 * 60 * 1000) return "online";
  if (ageMs < 30 * 60 * 1000) return "recent";
  return "stale";
}

const FRESHNESS_COLOR = {
  online: "var(--green, #4caf50)",
  recent: "var(--yellow, #f59e0b)",
  stale: "var(--text-muted)",
} as const;

const FRESHNESS_TITLE = {
  online: "Active in the last 5 minutes",
  recent: "Seen in the last 30 minutes",
  stale: "Not seen recently",
} as const;

/**
 * A single device row in the per-game device modal.
 * Status is derived from last_seen_at (updated by the server on every
 * authenticated request from that device — no TCP probe needed):
 *   green  = active in the last 5 minutes
 *   yellow = seen in the last 30 minutes
 *   grey   = stale / never seen
 */
function DeviceRow({ d, dim, displayIp }: { d: Device; dim: boolean; displayIp?: string | null }): React.ReactElement {
  const freshness = deviceFreshness(d.last_seen_at);
  const ip = displayIp ?? d.last_ip;
  return (
    <li style={{ padding: "6px 0", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 8, opacity: dim ? 0.6 : 1 }}>
      <span>🖥</span>
      <span>{d.name}</span>
      <span style={{ color: FRESHNESS_COLOR[freshness], fontSize: 14 }} title={FRESHNESS_TITLE[freshness]}>●</span>
      <span style={{ color: "var(--text-muted)", fontSize: 11 }}>{ip ?? "—"}</span>
    </li>
  );
}

/**
 * Per-game device modal: lists which paired devices have this game installed
 * vs. not, and offers ROM push (to a device that lacks it) or pull (from a
 * device that has it). Owns its own data fetch and transfer state — the parent
 * just hands it the game it's scoped to.
 */
export default function GameDeviceModal({ slug, name, gameConsole, gameIsLocal, onClose }: Props): React.ReactElement {
  const { devices: allDevices, currentDeviceId } = useDevices();
  const [localIp, setLocalIp] = useState<string | null>(null);
  const [installed, setInstalled] = useState<Device[] | null>(null);
  const [missing, setMissing] = useState<Device[] | null>(null);
  const [transfers, setTransfers] = useState<Record<string, TransferState>>({});

  useEffect(() => {
    window.emusync.server.localIp().then(setLocalIp).catch(() => {});
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const partial = await listGameDevices(slug);
        const installedIds = new Set(partial.map(d => d.id));
        const inst = partial.map(d => allDevices.find(a => a.id === d.id) ?? d);
        const miss = allDevices.filter(d => !installedIds.has(d.id));
        if (!cancelled) { setInstalled(inst); setMissing(miss); }
      } catch {
        if (!cancelled) { setInstalled([]); setMissing([]); }
      }
    })();
    return () => { cancelled = true; };
  }, [slug, allDevices]);

  function setTransfer(deviceId: string, state: TransferState): void {
    setTransfers(prev => ({ ...prev, [deviceId]: state }));
  }

  async function handlePush(toDevice: Device): Promise<void> {
    setTransfer(toDevice.id, { status: "loading", message: "" });
    const result = await window.emusync.rom.push(slug, toDevice.id, gameConsole);
    if (result.ok) {
      setTransfer(toDevice.id, {
        status: "success",
        message: result.targetOnline
          ? `${name} queued — ${toDevice.name} will receive it shortly`
          : `Queued — will deliver when ${toDevice.name} comes online`,
      });
    } else {
      setTransfer(toDevice.id, { status: "error", message: result.error || "Push failed" });
    }
  }

  async function handlePull(fromDevice: Device): Promise<void> {
    // Try to auto-resolve the local ROM folder from this device's console config
    let folder: string | null = null;
    if (currentDeviceId && gameConsole) {
      try {
        const consoles = await getDeviceConsoles(currentDeviceId);
        const match = consoles.find(c => c.console_name === gameConsole);
        if (match?.device_game_folder) folder = match.device_game_folder;
      } catch { /* fall through to picker */ }
    }

    // Fall back to folder picker if no console config found
    if (!folder) {
      folder = await window.emusync.dialog.openFolder();
      if (!folder) return;
    }

    setTransfer(fromDevice.id, { status: "loading", message: "" });
    try {
      const sourceGames = await getDeviceGameDevices(fromDevice.id);
      const sourceGame = sourceGames.find(g => g.slug === slug);
      if (!sourceGame?.rom_path) throw new Error("Source device has no ROM path for this game");
      const romFilename = sourceGame.rom_path.split("/").pop() ?? sourceGame.rom_path.split("\\").pop() ?? "rom";
      const destinationPath = folder.replace(/[\\/]$/, "") + "/" + romFilename;
      const result = await createPullRequest(slug, fromDevice.id, destinationPath);
      setTransfer(fromDevice.id, {
        status: "success",
        message: result.source_online
          ? `Pull requested — ${fromDevice.name} will send it shortly`
          : `Queued — will send when ${fromDevice.name} comes online`,
      });
    } catch (e: any) {
      setTransfer(fromDevice.id, { status: "error", message: e.message || "Pull request failed" });
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ width: 460 }} onClick={(e) => e.stopPropagation()}>
        <h3>Devices — {name}</h3>
        {installed === null ? (
          <div style={{ textAlign: "center", padding: "16px 0" }}>
            <span className="spinner" style={{ width: 20, height: 20 }} />
          </div>
        ) : (
          <>
            {installed.length > 0 && (
              <>
                <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "12px 0 4px" }}>Installed</p>
                <ul style={{ listStyle: "none", padding: 0, margin: "0 0 12px" }}>
                  {installed.map(d => {
                    const ts = transfers[d.id];
                    const canPull = !gameIsLocal && d.id !== currentDeviceId;
                    return (
                      <li key={d.id} style={{ borderBottom: "1px solid var(--border)" }}>
                        <DeviceRow d={d} dim={false} displayIp={d.id === currentDeviceId ? localIp : undefined} />
                        {canPull && (
                          <div style={{ padding: "4px 0 8px 28px" }}>
                            {!ts || ts.status === "idle" ? (
                              <button className="btn btn-ghost" style={{ fontSize: 12, padding: "3px 10px" }} onClick={() => handlePull(d)}>
                                ← Pull from {d.name}
                              </button>
                            ) : ts.status === "loading" ? (
                              <span style={{ fontSize: 12, color: "var(--text-muted)" }}><span className="spinner" style={{ width: 12, height: 12, marginRight: 6 }} />Requesting…</span>
                            ) : (
                              <span style={{ fontSize: 12, color: ts.status === "success" ? "var(--green)" : "var(--red)" }}>{ts.message}</span>
                            )}
                          </div>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </>
            )}
            {missing !== null && missing.length > 0 && (
              <>
                <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "12px 0 4px" }}>Not installed</p>
                <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                  {missing.map(d => {
                    const ts = transfers[d.id];
                    const canPush = gameIsLocal && d.id !== currentDeviceId;
                    return (
                      <li key={d.id} style={{ borderBottom: "1px solid var(--border)" }}>
                        <DeviceRow d={d} dim={true} displayIp={d.id === currentDeviceId ? localIp : undefined} />
                        {canPush && (
                          <div style={{ padding: "4px 0 8px 28px" }}>
                            {!ts || ts.status === "idle" ? (
                              <button className="btn btn-ghost" style={{ fontSize: 12, padding: "3px 10px" }} onClick={() => handlePush(d)}>
                                Push to {d.name} →
                              </button>
                            ) : ts.status === "loading" ? (
                              <span style={{ fontSize: 12, color: "var(--text-muted)" }}><span className="spinner" style={{ width: 12, height: 12, marginRight: 6 }} />Uploading…</span>
                            ) : (
                              <span style={{ fontSize: 12, color: ts.status === "success" ? "var(--green)" : "var(--red)" }}>{ts.message}</span>
                            )}
                          </div>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </>
            )}
            {installed.length === 0 && missing?.length === 0 && (
              <p style={{ color: "var(--text-muted)" }}>No paired devices found.</p>
            )}
            {installed.length === 0 && (missing?.length ?? 0) > 0 && (
              <p style={{ color: "var(--text-muted)", fontSize: 12, marginBottom: 8 }}>No devices have this game installed yet.</p>
            )}
          </>
        )}
        <div className="modal-actions">
          <button className="btn btn-ghost" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}
