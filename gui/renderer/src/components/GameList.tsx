import React, { useCallback, useEffect, useRef, useState } from "react";
import { listGames, removeGame, getSaveMeta, getLock, pushGameSaves, getGameDevice, listDevices, getSaveDeviceCount, type Game, type Device } from "../api";
import ConsoleImport from "./ConsoleImport";

type Props = {
  onAdd: () => void;
  onEdit: (game: Game) => void;
  onPlay: (slug: string, name: string) => void;
};

type GameRow = Game & {
  lastPush?: string;
  lastSave?: string | null;
  locked?: boolean;
  syncing?: boolean;
  deviceCount?: number;
  totalDevices?: number;
};

type ConfirmRemove = { slug: string; name: string } | null;

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

export default function GameList({ onAdd, onEdit, onPlay }: Props): React.ReactElement {
  const [games, setGames] = useState<GameRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [confirmRemove, setConfirmRemove] = useState<ConfirmRemove>(null);
  const [removing, setRemoving] = useState(false);
  const [showEmulatorImport, setShowEmulatorImport] = useState(false);
  const [syncingSlug, setSyncingSlug] = useState<string | null>(null);
  const [selectedSlugs, setSelectedSlugs] = useState<Set<string>>(new Set());
  const [confirmBulkDelete, setConfirmBulkDelete] = useState(false);
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [collapsedConsoles, setCollapsedConsoles] = useState<Set<string>>(new Set());
  const [colWidths, setColWidths] = useState({ name: 260, lastSave: 150, synced: 150, device: 140 });
  const [sortBy, setSortBy] = useState<'default' | 'game' | 'lastSave' | 'synced'>('default');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');

  const resizingCol = useRef<keyof typeof colWidths | null>(null);
  const resizeStartX = useRef(0);
  const resizeStartWidth = useRef(0);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [raw, devices] = await Promise.all([listGames(), listDevices()]);
      const totalDevices = devices.length;
      const enriched = await Promise.all(
        raw.map(async (g): Promise<GameRow> => {
          const [meta, lock, config, deviceCount] = await Promise.allSettled([getSaveMeta(g.slug), getLock(g.slug), getGameDevice(g.slug), getSaveDeviceCount(g.slug)]);
          let lastSave: string | null = undefined;
          if (config.status === "fulfilled" && config.value?.save_path) {
            lastSave = await (window as any).emusync.files.getSaveTime(config.value.save_path);
          }
          const count = deviceCount.status === "fulfilled" ? deviceCount.value.device_count : 0;
          return {
            ...g,
            lastPush: meta.status === "fulfilled" && meta.value ? meta.value.pushed_at.slice(0, 19) : undefined,
            lastSave,
            locked: lock.status === "fulfilled" ? lock.value.locked : false,
            deviceCount: count,
            totalDevices,
          };
        })
      );
      setGames(enriched);
    } catch {
      // Server offline — show empty list, StatusBadge shows the offline indicator
      setGames([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

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

  async function handleSync(slug: string): Promise<void> {
    setSyncingSlug(slug);
    try {
      await pushGameSaves(slug);
      await load();
    } catch {
      /* error — keep UI responsive */
    } finally {
      setSyncingSlug(null);
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
        <div className="game-table" style={{ gridTemplateColumns: `32px ${colWidths.name}px ${colWidths.lastSave}px ${colWidths.synced}px ${colWidths.device}px 1fr` }}>
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
          <div className="col-header">Device <span className="resize-handle" onMouseDown={startResize("device")} /></div>
          <div className="col-header">Actions</div>

          {(() => {
            const grouped = games.reduce<Record<string, GameRow[]>>((acc, g) => {
              const key = g.console || "Other";
              (acc[key] ??= []).push(g);
              return acc;
            }, {});
            let consoleKeys = Object.keys(grouped).sort();

            // If sorting by game, also sort console headers in the same direction
            if (sortBy === 'game' && sortDir === 'desc') {
              consoleKeys = consoleKeys.reverse();
            }

            return consoleKeys.map(key => (
              <React.Fragment key={key}>
                {/* Console section header spans all columns */}
                <div className="console-section-header" style={{ gridColumn: "1 / -1" }} onClick={() => toggleConsole(key)}>
                  <ConsoleCheckbox
                    games={grouped[key]}
                    selectedSlugs={selectedSlugs}
                    onToggle={() => toggleConsoleSelection(key, grouped[key])}
                  />
                  <span>{collapsedConsoles.has(key) ? "▶" : "▼"}</span>
                  <span style={{ flex: 1 }}>{key}</span>
                  <span style={{ color: "var(--text-muted)", fontSize: 12 }}>{grouped[key].length} game{grouped[key].length !== 1 ? "s" : ""}</span>
                </div>

                {/* Game rows — each game is 5 grid cells */}
                {!collapsedConsoles.has(key) && getSortedGamesInConsole(grouped[key]).map((g) => (
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
                      {g.lastSave ? g.lastSave : "No save locally"}
                    </div>
                    <div className="game-cell game-cell-muted">
                      {g.locked && <span style={{ color: "var(--red)", marginRight: 6 }}>🔒</span>}
                      <span>{g.lastPush ? g.lastPush : "Never synced"}</span>
                    </div>
                    <div className="game-cell">
                      {g.deviceCount !== undefined && g.totalDevices ? (
                        <button className="btn btn-sm btn-ghost" title={`Saved on ${g.deviceCount} of ${g.totalDevices} device${g.totalDevices !== 1 ? 's' : ''}`}>
                          {g.deviceCount}/{g.totalDevices}
                        </button>
                      ) : (
                        <span className="game-cell-muted">—</span>
                      )}
                    </div>
                    <div className="game-cell game-cell-actions">
                      <button
                        className="btn btn-icon"
                        title="Push saves to devices"
                        disabled={g.locked || syncingSlug === g.slug}
                        onClick={() => handleSync(g.slug)}
                      >
                        {syncingSlug === g.slug ? <span className="spinner" style={{ width: 12, height: 12 }} /> : "↑"}
                      </button>
                      <button
                        className="btn btn-icon"
                        title="Play"
                        disabled={g.locked}
                        onClick={() => onPlay(g.slug, g.name)}
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
            ));
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
