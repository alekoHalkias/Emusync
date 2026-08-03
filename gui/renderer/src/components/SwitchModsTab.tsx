// Communal Switch mod pool viewer (issue #444): lists every mod folder found
// under Eden's load/<title-id>/ on this device, merged with what's in the
// shared server pool, plus a manual "Sync now" trigger. Mod folders can be
// gigabytes, so nothing here transfers automatically or re-verifies content —
// see cli/run_switch.py's _sync_switch_mods for the actual name-only sync.
import React, { useEffect, useState } from "react";
import { getGame, listSwitchMods, SwitchModPoolEntry } from "../api";

function fmtSize(n: number): string {
  if (!n) return "?";
  const units = ["B", "KB", "MB", "GB"];
  let size = n;
  let i = 0;
  while (size >= 1024 && i < units.length - 1) { size /= 1024; i++; }
  return `${size.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

export default function SwitchModsTab({ slug }: { slug: string }): React.ReactElement {
  const [titleId, setTitleId] = useState<string | null>(null);
  const [local, setLocal] = useState<string[]>([]);
  const [pool, setPool] = useState<SwitchModPoolEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  async function load(): Promise<void> {
    setLoading(true);
    setError(null);
    try {
      const game = await getGame(slug);
      const id = game.switch_title_id || "";
      setTitleId(id);
      if (!id) { setLoading(false); return; }
      const [localMods, poolMods] = await Promise.all([
        window.emusync.switchMods.listLocal(id),
        listSwitchMods(id).catch(() => []),
      ]);
      setLocal(localMods);
      setPool(poolMods);
    } catch (e: any) {
      setError(e.message || "Failed to load mods");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [slug]);

  async function sync(): Promise<void> {
    setSyncing(true);
    setStatus(null);
    try {
      const res = await window.emusync.switchMods.sync(slug);
      setStatus(res.output || (res.ok ? "Already in sync." : "Sync failed."));
      await load();
    } finally {
      setSyncing(false);
    }
  }

  async function reveal(): Promise<void> {
    if (!titleId) return;
    const res = await window.emusync.switchMods.reveal(titleId);
    if (!res.ok) setStatus(res.error || "Could not open folder");
  }

  if (loading) return <p style={{ color: "var(--text-muted)" }}>Loading…</p>;
  if (error) return <p style={{ color: "var(--danger, #e05555)" }}>{error}</p>;
  if (!titleId) {
    return (
      <p style={{ color: "var(--text-muted)" }}>
        This game's Switch title ID isn't known yet — launch it once via Run so its mod folder can be discovered.
      </p>
    );
  }

  const names = Array.from(new Set([...local, ...pool.map((m) => m.mod_name)])).sort();

  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <button className="btn btn-primary" onClick={sync} disabled={syncing}>
          {syncing ? "Syncing…" : "Sync mods now"}
        </button>
        <button className="btn btn-ghost" onClick={reveal}>Open mods folder</button>
      </div>

      {names.length === 0 ? (
        <p style={{ color: "var(--text-muted)" }}>No mods found locally or in the shared pool for this game.</p>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: "left", color: "var(--text-muted)", fontSize: 11, textTransform: "uppercase" }}>
              <th style={{ padding: "4px 6px" }}>Mod</th>
              <th style={{ padding: "4px 6px" }}>Local</th>
              <th style={{ padding: "4px 6px" }}>Pool</th>
              <th style={{ padding: "4px 6px" }}>Size</th>
            </tr>
          </thead>
          <tbody>
            {names.map((name) => {
              const inLocal = local.includes(name);
              const poolEntry = pool.find((m) => m.mod_name === name);
              return (
                <tr key={name} style={{ borderTop: "1px solid var(--border)" }}>
                  <td style={{ padding: "6px" }}>{name}</td>
                  <td style={{ padding: "6px" }}>{inLocal ? "✓" : ""}</td>
                  <td style={{ padding: "6px" }}>{poolEntry ? "✓" : ""}</td>
                  <td style={{ padding: "6px" }}>{poolEntry ? fmtSize(poolEntry.size) : "?"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {status && <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 12, whiteSpace: "pre-wrap" }}>{status}</p>}
    </div>
  );
}
