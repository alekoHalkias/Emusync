import React, { useCallback, useEffect, useRef, useState } from "react";
import { listGames, removeGame, getSaveMeta, getLock, getGameDevice, listGameDevices, getDeviceGameDevices, getDeviceConsoles, createPullRequest, type Game, type Device } from "../api";
import ConsoleImport from "./ConsoleImport";
import { useDevices } from "../DeviceContext";

type Props = {
  onAdd: () => void;
  onEdit: (game: Game) => void;
  onPlay: (slug: string, name: string) => void;
};

type GameRow = Game & {
  lastPush?: string;
  lastSave?: string | null;
  locked?: boolean;
  isLocal: boolean;
};

type ConfirmRemove = { slug: string; name: string } | null;
type TransferState = { status: "idle" | "loading" | "success" | "error"; message: string };

type DeviceModal = {
  slug: string;
  name: string;
  gameConsole: string;
  gameIsLocal: boolean;          // true = current device has rom_path for this game
  installed: Device[] | null;   // devices that have the game
  missing: Device[] | null;     // paired devices that don't
  transfers: Record<string, TransferState>;
} | null;

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

function ConsoleCheckbox({ games, selectedSlugs, onToggle }: {
  games: GameRow[]; selectedSlugs: Set<string>; onToggle: () => void;
}): React.ReactElement {
  const ref = useRef<HTMLInputElement>(null);
  const selected = games.filter(g => selectedSlugs.has(g.slug)).length;
  const allSelected = selected === games.length && games.length > 0;
  const someSelected = selected > 0 && !allSelected;

  useEffect(() => {
    if (ref.current) ref.current.indeterminate = someSelected;
  }, [someSelected]);

  return (
    <input
      ref={ref}
      type="checkbox"
      checked={allSelected}
      onChange={onToggle}
      style={{ cursor: "pointer", marginRight: 8 }}
      onClick={(e) => e.stopPropagation()}
      title={allSelected ? "Deselect all in this console" : "Select all in this console"}
    />
  );
}

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

export default function GameList({ onAdd, onEdit, onPlay }: Props): React.ReactElement {
  const { devices: allDevices, currentDeviceId } = useDevices();
  const [localIp, setLocalIp] = useState<string | null>(null);
  const [games, setGames] = useState<GameRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [confirmRemove, setConfirmRemove] = useState<ConfirmRemove>(null);
  const [removing, setRemoving] = useState(false);
  const [showEmulatorImport, setShowEmulatorImport] = useState(false);
  const [selectedSlugs, setSelectedSlugs] = useState<Set<string>>(new Set());
  const [confirmBulkDelete, setConfirmBulkDelete] = useState(false);
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [collapsedConsoles, setCollapsedConsoles] = useState<Set<string>>(new Set());
  const [collapsedSections, setCollapsedSections] = useState<Set<string>>(new Set());
  const [deviceModal, setDeviceModal] = useState<DeviceModal>(null);
  const [colWidths, setColWidths] = useState({ name: 260, lastSave: 150, synced: 150 });
  const [sortBy, setSortBy] = useState<'default' | 'game' | 'lastSave' | 'synced'>('default');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');

  const resizingCol = useRef<keyof typeof colWidths | null>(null);
  const resizeStartX = useRef(0);
  const resizeStartWidth = useRef(0);
  const loadIdRef = useRef(0);

  const load = useCallback(async (silent = false) => {
    const thisId = ++loadIdRef.current;
    if (!silent) setLoading(true);
    try {
      const raw = await listGames();
      const enriched = await Promise.all(
        raw.map(async (g): Promise<GameRow> => {
          const [meta, lock, config] = await Promise.allSettled([getSaveMeta(g.slug), getLock(g.slug), getGameDevice(g.slug)]);
          // A game is local if this device has ANY config row for it (save path, rom path, etc.).
          // Requiring rom_path would incorrectly hide games added with only a save path.
          const isLocal = config.status === "fulfilled";
          let lastSave: string | null = null;
          if (config.status === "fulfilled" && config.value?.save_path) {
            lastSave = await (window as any).emusync.files.getSaveTime(config.value.save_path);
          }
          return {
            ...g,
            lastPush: meta.status === "fulfilled" && meta.value ? meta.value.pushed_at.slice(0, 19) : undefined,
            lastSave,
            locked: lock.status === "fulfilled" ? lock.value.locked : false,
            isLocal,
          };
        })
      );
      // Discard results from a superseded load (a newer call started while this was in flight)
      if (loadIdRef.current !== thisId) return;
      setGames(enriched);
    } catch {
      if (loadIdRef.current !== thisId) return;
      // Server offline — show empty list, StatusBadge shows the offline indicator
      if (!silent) setGames([]);
    } finally {
      if (loadIdRef.current !== thisId) return;
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const id = setInterval(() => load(true), 5000);
    return () => clearInterval(id);
  }, [load]);

  useEffect(() => {
    (window as any).emusync.server.localIp().then(setLocalIp).catch(() => {});
  }, []);

  async function handleRemove(): Promise<void> {
    if (!confirmRemove) return;
    setRemoving(true);
    try {
      await removeGame(confirmRemove.slug);
      setConfirmRemove(null);
      await load();
    } catch {
      /* ignore — game might not exist */
    } finally {
      setRemoving(false);
    }
  }

  async function handleOpenDeviceModal(g: GameRow): Promise<void> {
    const { slug, name, console: gameConsole = "", isLocal: gameIsLocal } = g;
    const blank = { slug, name, gameConsole, gameIsLocal, installed: null, missing: null, transfers: {} };
    setDeviceModal(blank);
    try {
      const partial = await listGameDevices(slug);
      const installedIds = new Set(partial.map(d => d.id));
      const installed = partial.map(d => allDevices.find(a => a.id === d.id) ?? d);
      const missing = allDevices.filter(d => !installedIds.has(d.id));
      setDeviceModal({ ...blank, installed, missing });
    } catch {
      setDeviceModal({ ...blank, installed: [], missing: [] });
    }
  }

  function setTransfer(deviceId: string, state: TransferState): void {
    setDeviceModal(prev => prev ? { ...prev, transfers: { ...prev.transfers, [deviceId]: state } } : prev);
  }

  async function handlePush(toDevice: Device): Promise<void> {
    if (!deviceModal) return;
    setTransfer(toDevice.id, { status: "loading", message: "" });
    const result = await (window as any).emusync.rom.push(deviceModal.slug, toDevice.id, deviceModal.gameConsole);
    if (result.ok) {
      setTransfer(toDevice.id, {
        status: "success",
        message: result.targetOnline
          ? `${deviceModal.name} queued — ${toDevice.name} will receive it shortly`
          : `Queued — will deliver when ${toDevice.name} comes online`,
      });
    } else {
      setTransfer(toDevice.id, { status: "error", message: result.error || "Push failed" });
    }
  }

  async function handlePull(fromDevice: Device): Promise<void> {
    if (!deviceModal) return;

    // Try to auto-resolve the local ROM folder from this device's console config
    let folder: string | null = null;
    if (currentDeviceId && deviceModal.gameConsole) {
      try {
        const consoles = await getDeviceConsoles(currentDeviceId);
        const match = consoles.find(c => c.console_name === deviceModal.gameConsole);
        if (match?.device_game_folder) folder = match.device_game_folder;
      } catch { /* fall through to picker */ }
    }

    // Fall back to folder picker if no console config found
    if (!folder) {
      folder = await (window as any).emusync.dialog.openFolder();
      if (!folder) return;
    }

    setTransfer(fromDevice.id, { status: "loading", message: "" });
    try {
      const sourceGames = await getDeviceGameDevices(fromDevice.id);
      const sourceGame = sourceGames.find(g => g.slug === deviceModal.slug);
      if (!sourceGame?.rom_path) throw new Error("Source device has no ROM path for this game");
      const romFilename = sourceGame.rom_path.split("/").pop() ?? sourceGame.rom_path.split("\\").pop() ?? "rom";
      const destinationPath = folder.replace(/[\\/]$/, "") + "/" + romFilename;
      const result = await createPullRequest(deviceModal.slug, fromDevice.id, destinationPath);
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

  function toggleSelection(slug: string): void {
    setSelectedSlugs(prev => {
      const next = new Set(prev);
      next.has(slug) ? next.delete(slug) : next.add(slug);
      return next;
    });
  }

  function toggleConsoleSelection(consoleKey: string, consoleGames: GameRow[]): void {
    const consoleSlugs = consoleGames.map(g => g.slug);
    const allSelected = consoleSlugs.every(s => selectedSlugs.has(s));
    setSelectedSlugs(prev => {
      const next = new Set(prev);
      if (allSelected) {
        consoleSlugs.forEach(s => next.delete(s));
      } else {
        consoleSlugs.forEach(s => next.add(s));
      }
      return next;
    });
  }

  function toggleConsole(consoleKey: string): void {
    setCollapsedConsoles(prev => {
      const next = new Set(prev);
      next.has(consoleKey) ? next.delete(consoleKey) : next.add(consoleKey);
      return next;
    });
  }

  async function handleBulkDelete(): Promise<void> {
    setBulkDeleting(true);
    const slugsToDelete = Array.from(selectedSlugs);
    const errs: string[] = [];
    for (const slug of slugsToDelete) {
      try {
        await removeGame(slug);
      } catch (e) {
        errs.push(slug);
      }
    }
    // Close modal and clear state
    setConfirmBulkDelete(false);
    setSelectedSlugs(new Set());
    setBulkDeleting(false);
    // Reload games after deletion
    await load();
    if (errs.length > 0) {
      console.error(`Failed to delete ${errs.length} game(s):`, errs);
    }
  }

  function startResize(col: keyof typeof colWidths) {
    return (e: React.MouseEvent<HTMLDivElement>) => {
      e.preventDefault();
      resizingCol.current = col;
      resizeStartX.current = e.clientX;
      resizeStartWidth.current = colWidths[col];
    };
  }

  function handleSort(col: 'game' | 'lastSave' | 'synced') {
    if (sortBy === col) {
      // Same column: toggle direction
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    } else {
      // Different column: set new column and reset to asc
      setSortBy(col);
      setSortDir('asc');
    }
  }

  function getSortedGamesInConsole(consoleGames: GameRow[]): GameRow[] {
    if (sortBy === 'default') {
      return consoleGames; // unsorted
    }

    const sorted = [...consoleGames];
    const mult = sortDir === 'asc' ? 1 : -1;

    if (sortBy === 'game') {
      sorted.sort((a, b) => mult * a.name.localeCompare(b.name));
    } else if (sortBy === 'lastSave') {
      sorted.sort((a, b) => {
        const aTime = a.lastSave || '';
        const bTime = b.lastSave || '';
        return mult * aTime.localeCompare(bTime);
      });
    } else if (sortBy === 'synced') {
      sorted.sort((a, b) => {
        const aTime = a.lastPush || '';
        const bTime = b.lastPush || '';
        return mult * aTime.localeCompare(bTime);
      });
    }

    return sorted;
  }

  useEffect(() => {
    function onMove(e: MouseEvent) {
      if (!resizingCol.current) return;
      const delta = e.clientX - resizeStartX.current;
      setColWidths(prev => ({
        ...prev,
        [resizingCol.current!]: Math.max(80, resizeStartWidth.current + delta),
      }));
    }
    function onUp() { resizingCol.current = null; }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);

  return (
    <>
      <div className="section-header">
        <h2>Games</h2>
        <div style={{ display: "flex", gap: 8 }}>
          {selectedSlugs.size > 0 && (
            <button className="btn btn-danger" onClick={() => setConfirmBulkDelete(true)}>
              🗑 Delete {selectedSlugs.size}
            </button>
          )}
          <button className="btn btn-ghost" onClick={() => setShowEmulatorImport(true)}>Bulk import</button>
        </div>
      </div>

      {loading ? (
        <div style={{ textAlign: "center", padding: 40 }}>
          <span className="spinner" style={{ width: 24, height: 24 }} />
        </div>
      ) : games.length === 0 ? (
        <div className="empty-state">
          <h3>No games yet</h3>
          <p style={{ marginBottom: 20 }}>Add your first game to start syncing saves.</p>
          <button className="btn btn-primary" onClick={onAdd}>+ Add game</button>
        </div>
      ) : (
        <div className="game-table" style={{ gridTemplateColumns: `32px ${colWidths.name}px ${colWidths.lastSave}px ${colWidths.synced}px 1fr` }}>
          {/* Column headers */}
          <div className="col-header" />
          <div className="col-header sortable" onMouseDown={(e) => { if ((e.target as HTMLElement).closest('.resize-handle') === null) handleSort('game'); }} title="Click to sort">
            Game {sortBy === 'game' && <span style={{ marginLeft: 4 }}>{sortDir === 'asc' ? '▲' : '▼'}</span>} <span className="resize-handle" onMouseDown={startResize("name")} />
          </div>
          <div className="col-header sortable" onMouseDown={(e) => { if ((e.target as HTMLElement).closest('.resize-handle') === null) handleSort('lastSave'); }} title="Click to sort">
            Last Saved {sortBy === 'lastSave' && <span style={{ marginLeft: 4 }}>{sortDir === 'asc' ? '▲' : '▼'}</span>} <span className="resize-handle" onMouseDown={startResize("lastSave")} />
          </div>
          <div className="col-header sortable" onMouseDown={(e) => { if ((e.target as HTMLElement).closest('.resize-handle') === null) handleSort('synced'); }} title="Click to sort">
            Synced {sortBy === 'synced' && <span style={{ marginLeft: 4 }}>{sortDir === 'asc' ? '▲' : '▼'}</span>} <span className="resize-handle" onMouseDown={startResize("synced")} />
          </div>
          <div className="col-header">Actions</div>

          {(() => {
            const localGames = games.filter(g => g.isLocal);
            const otherGames = games.filter(g => !g.isLocal);

            function groupByConsole(list: GameRow[]): [string, GameRow[]][] {
              const grouped = list.reduce<Record<string, GameRow[]>>((acc, g) => {
                const key = g.console || "Other";
                (acc[key] ??= []).push(g);
                return acc;
              }, {});
              let keys = Object.keys(grouped).sort();
              if (sortBy === "game" && sortDir === "desc") keys = keys.reverse();
              return keys.map(k => [k, grouped[k]]);
            }

            function renderConsoleGroups(list: GameRow[], keyPrefix: string, canPlay: boolean) {
              return groupByConsole(list).map(([key, consoleGames]) => {
                const colKey = keyPrefix + key;
                return (
                  <React.Fragment key={colKey}>
                    <div className="console-section-header" style={{ gridColumn: "1 / -1" }} onClick={() => toggleConsole(colKey)}>
                      <ConsoleCheckbox
                        games={consoleGames}
                        selectedSlugs={selectedSlugs}
                        onToggle={() => toggleConsoleSelection(colKey, consoleGames)}
                      />
                      <span>{collapsedConsoles.has(colKey) ? "▶" : "▼"}</span>
                      <span style={{ flex: 1 }}>{key}</span>
                      <span style={{ color: "var(--text-muted)", fontSize: 12 }}>{consoleGames.length} game{consoleGames.length !== 1 ? "s" : ""}</span>
                    </div>

                    {!collapsedConsoles.has(colKey) && getSortedGamesInConsole(consoleGames).map((g) => (
                      <React.Fragment key={g.slug}>
                        <div className="game-cell">
                          <input
                            type="checkbox"
                            checked={selectedSlugs.has(g.slug)}
                            onChange={() => toggleSelection(g.slug)}
                            style={{ cursor: "pointer" }}
                          />
                        </div>
                        <div className="game-cell game-cell-name">{g.name}</div>
                        <div className="game-cell game-cell-muted">
                          {canPlay ? (g.lastSave ? g.lastSave : "No save locally") : "—"}
                        </div>
                        <div className="game-cell game-cell-muted">
                          {g.locked && <span style={{ color: "var(--red)", marginRight: 6 }}>🔒</span>}
                          <span>{g.lastPush ? g.lastPush : "Never synced"}</span>
                        </div>
                        <div className="game-cell game-cell-actions">
                          <button
                            className="btn btn-icon"
                            title="Show devices with this game"
                            onClick={() => handleOpenDeviceModal(g)}
                          >
                            🖥
                          </button>
                          <button
                            className="btn btn-icon"
                            title="Play"
                            disabled={g.locked || !canPlay}
                            onClick={() => canPlay && onPlay(g.slug, g.name)}
                          >
                            ▶
                          </button>
                          <button
                            className="btn btn-icon"
                            title="Settings"
                            onClick={() => onEdit(g)}
                          >
                            ⚙
                          </button>
                          <button
                            className="btn btn-icon"
                            title="Remove from EmuSync"
                            onClick={() => setConfirmRemove({ slug: g.slug, name: g.name })}
                          >
                            🗑
                          </button>
                        </div>
                      </React.Fragment>
                    ))}
                  </React.Fragment>
                );
              });
            }

            const localCollapsed  = collapsedSections.has("local");
            const otherCollapsed  = collapsedSections.has("other");
            const toggleSection   = (key: string) => setCollapsedSections(prev => {
              const next = new Set(prev);
              next.has(key) ? next.delete(key) : next.add(key);
              return next;
            });

            return (
              <>
                {/* ── On this device ── */}
                <div
                  className="device-section-header"
                  style={{ gridColumn: "1 / -1", cursor: "pointer" }}
                  onClick={() => toggleSection("local")}
                >
                  <span style={{ marginRight: 6, fontSize: 11 }}>{localCollapsed ? "▶" : "▼"}</span>
                  On this device
                  <span style={{ color: "var(--text-muted)", fontSize: 12, fontWeight: 400, marginLeft: 8 }}>{localGames.length} game{localGames.length !== 1 ? "s" : ""}</span>
                </div>
                {!localCollapsed && (localGames.length === 0 ? (
                  <div style={{ gridColumn: "1 / -1", padding: "16px 12px", color: "var(--text-muted)", fontSize: 13 }}>
                    No games configured on this device yet. Use Bulk import or Add game.
                  </div>
                ) : renderConsoleGroups(localGames, "", true))}

                {/* ── On other devices ── */}
                {otherGames.length > 0 && (
                  <>
                    <div
                      className="device-section-header"
                      style={{ gridColumn: "1 / -1", marginTop: 8, cursor: "pointer" }}
                      onClick={() => toggleSection("other")}
                    >
                      <span style={{ marginRight: 6, fontSize: 11 }}>{otherCollapsed ? "▶" : "▼"}</span>
                      On other devices
                      <span style={{ color: "var(--text-muted)", fontSize: 12, fontWeight: 400, marginLeft: 8 }}>{otherGames.length} game{otherGames.length !== 1 ? "s" : ""}</span>
                    </div>
                    {!otherCollapsed && renderConsoleGroups(otherGames, "other:", false)}
                  </>
                )}
              </>
            );
          })()}
        </div>
      )}

      {showEmulatorImport && (
        <ConsoleImport
          onClose={() => setShowEmulatorImport(false)}
          onImported={load}
        />
      )}

      {confirmRemove && (
        <div className="modal-overlay" onClick={() => setConfirmRemove(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Remove {confirmRemove.name}?</h3>
            <p>
              This removes the game from EmuSync management. The save file on your
              device will <strong>not</strong> be deleted.
            </p>
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setConfirmRemove(null)} disabled={removing}>
                Cancel
              </button>
              <button className="btn btn-danger" onClick={handleRemove} disabled={removing}>
                {removing ? <><span className="spinner" /> Removing…</> : "Remove"}
              </button>
            </div>
          </div>
        </div>
      )}

      {deviceModal && (
        <div className="modal-overlay" onClick={() => setDeviceModal(null)}>
          <div className="modal" style={{ width: 460 }} onClick={(e) => e.stopPropagation()}>
            <h3>Devices — {deviceModal.name}</h3>
            {deviceModal.installed === null ? (
              <div style={{ textAlign: "center", padding: "16px 0" }}>
                <span className="spinner" style={{ width: 20, height: 20 }} />
              </div>
            ) : (
              <>
                {deviceModal.installed.length > 0 && (
                  <>
                    <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "12px 0 4px" }}>Installed</p>
                    <ul style={{ listStyle: "none", padding: 0, margin: "0 0 12px" }}>
                      {deviceModal.installed.map(d => {
                        const ts = deviceModal.transfers[d.id];
                        const canPull = !deviceModal.gameIsLocal && d.id !== currentDeviceId;
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
                {deviceModal.missing !== null && deviceModal.missing.length > 0 && (
                  <>
                    <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "12px 0 4px" }}>Not installed</p>
                    <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                      {deviceModal.missing.map(d => {
                        const ts = deviceModal.transfers[d.id];
                        const canPush = deviceModal.gameIsLocal && d.id !== currentDeviceId;
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
                {deviceModal.installed.length === 0 && deviceModal.missing?.length === 0 && (
                  <p style={{ color: "var(--text-muted)" }}>No paired devices found.</p>
                )}
                {deviceModal.installed.length === 0 && (deviceModal.missing?.length ?? 0) > 0 && (
                  <p style={{ color: "var(--text-muted)", fontSize: 12, marginBottom: 8 }}>No devices have this game installed yet.</p>
                )}
              </>
            )}
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setDeviceModal(null)}>Close</button>
            </div>
          </div>
        </div>
      )}

      {confirmBulkDelete && (
        <div className="modal-overlay" onClick={() => setConfirmBulkDelete(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Delete {selectedSlugs.size} game{selectedSlugs.size !== 1 ? "s" : ""}?</h3>
            <p>
              This removes the selected games from EmuSync management. The save files on your
              devices will <strong>not</strong> be deleted.
            </p>
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setConfirmBulkDelete(false)} disabled={bulkDeleting}>
                Cancel
              </button>
              <button className="btn btn-danger" onClick={handleBulkDelete} disabled={bulkDeleting}>
                {bulkDeleting ? <><span className="spinner" /> Deleting…</> : "Yes, delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
