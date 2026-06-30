import React, { useEffect, useRef, useState } from "react";
import { removeGame, setGameDevice } from "../api";
import ConsoleImport from "./ConsoleImport";
import NetworkPlaySetup from "./NetworkPlaySetup";
import { RelTime } from "../time";
import GameModal, { type GameModalTarget } from "./GameModal";
import { useGameList } from "./game-list/useGameList";
import { groupByConsole, sortGamesInConsole, lastActivity } from "./game-list/helpers";
import type { GameRow, SortBy, SortDir } from "./game-list/types";

type Props = {
  onAdd: () => void;
  onPlay: (slug: string, name: string) => void;
  importOpen: boolean;                       // Bulk-import modal, lifted to the topbar
  onImportOpenChange: (open: boolean) => void;
};

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

export default function GameList({ onAdd, onPlay, importOpen, onImportOpenChange }: Props): React.ReactElement {
  const { games, loading, reload } = useGameList();
  const [gameModal, setGameModal] = useState<GameModalTarget | null>(null);
  const [netPlayTarget, setNetPlayTarget] = useState<{ slug: string; name: string } | null>(null);
  const [searchingSlug, setSearchingSlug] = useState<string | null>(null);
  const [selectedSlugs, setSelectedSlugs] = useState<Set<string>>(new Set());
  const [confirmBulkDelete, setConfirmBulkDelete] = useState(false);
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [collapsedConsoles, setCollapsedConsoles] = useState<Set<string>>(new Set());
  const [collapsedSections, setCollapsedSections] = useState<Set<string>>(new Set());
  const [colWidths, setColWidths] = useState({ name: 260, activity: 180 });
  const [sortBy, setSortBy] = useState<SortBy>('default');
  const [sortDir, setSortDir] = useState<SortDir>('asc');

  const resizingCol = useRef<keyof typeof colWidths | null>(null);
  const resizeStartX = useRef(0);
  const resizeStartWidth = useRef(0);

  async function searchAndImportAll(otherGames: GameRow[]): Promise<void> {
    if (searchingSlug) return;
    setSearchingSlug("bulk");
    try {
      const cfg = await window.emusync.config.load();
      const allConsoles = (await window.emusync.emulator.consoles().catch(() => [])) ?? [];

      // Group other-device games by console key so we scan each mount once
      const byConsoleKey = new Map<string, { key: string; mount: string; emulator: any; games: GameRow[] }>();
      for (const g of otherGames) {
        const found = allConsoles.find(
          (c: { key: string; label: string; abbr?: string }) =>
            c.label === g.console || c.abbr === g.console || c.key === g.console,
        );
        if (!found) continue;
        if (byConsoleKey.has(found.key)) {
          byConsoleKey.get(found.key)!.games.push(g);
          continue;
        }
        const recentFolders = cfg?.recent_import_folders?.[found.key];
        if (!recentFolders || recentFolders.length === 0) continue;
        const mount = recentFolders[0];
        const { options } = await window.emusync.emulator.detect(found.key).catch(() => ({ options: [] }));
        if (!options || options.length === 0) continue;
        byConsoleKey.set(found.key, { key: found.key, mount, emulator: options[0], games: [g] });
      }

      let imported = 0;
      for (const { key, mount, emulator, games } of byConsoleKey.values()) {
        const scanResult = await window.emusync.emulator.scan(key, emulator, [mount]).catch(() => null);
        if (!scanResult?.roms || scanResult.roms.length === 0) continue;

        for (const g of games) {
          // Match scanned ROMs to this game by slug or name
          const rom = scanResult.roms.find((r: any) =>
            r.romPath && (
              r.name?.toLowerCase() === g.name.toLowerCase() ||
              r.romFileName?.toLowerCase().replace(/\.[^.]+$/, "") === g.name.toLowerCase()
            ),
          ) || scanResult.roms.find((r: any) => r.romPath);

          if (!rom?.romPath) continue;
          try {
            await setGameDevice(g.slug, {
              rom_source: "network",
              rom_path: rom.romPath,
              save_path: rom.savePath,
              state_path: rom.statePath || "",
              launch_command: rom.launchCommand,
              rom_folder_path: mount,
            });
            imported++;
          } catch { /* skip this game */ }
        }
      }

      if (imported > 0) reload(true);
    } finally {
      setSearchingSlug(null);
    }
  }

  function openGameModal(g: GameRow, canPlay: boolean): void {
    setGameModal({
      slug: g.slug, name: g.name, gameConsole: g.console || "",
      gameIsLocal: g.isLocal, savePath: g.savePath, statePath: g.statePath, canPlay,
    });
  }

  function toggleSelection(slug: string): void {
    setSelectedSlugs(prev => {
      const next = new Set(prev);
      next.has(slug) ? next.delete(slug) : next.add(slug);
      return next;
    });
  }

  function toggleConsoleSelection(consoleGames: GameRow[]): void {
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
    await reload();
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

  function handleSort(col: 'game' | 'activity') {
    if (sortBy === col) {
      // Same column: toggle direction
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    } else {
      // Different column: set new column and reset to asc
      setSortBy(col);
      setSortDir('asc');
    }
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
      {/* Contextual bulk-delete bar — only shown while games are selected, so
          there's no persistent header line (Bulk import lives in the topbar). */}
      {selectedSlugs.size > 0 && (
        <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 8 }}>
          <button className="btn btn-danger" onClick={() => setConfirmBulkDelete(true)}>
            🗑 Delete {selectedSlugs.size}
          </button>
        </div>
      )}

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
        <div className="game-table" style={{ gridTemplateColumns: `32px ${colWidths.name}px ${colWidths.activity}px 44px 1fr` }}>
          {/* Column headers */}
          <div className="col-header" />
          <div className="col-header sortable" onMouseDown={(e) => { if ((e.target as HTMLElement).closest('.resize-handle') === null) handleSort('game'); }} title="Click to sort">
            Game {sortBy === 'game' && <span style={{ marginLeft: 4 }}>{sortDir === 'asc' ? '▲' : '▼'}</span>} <span className="resize-handle" onMouseDown={startResize("name")} />
          </div>
          <div className="col-header sortable" onMouseDown={(e) => { if ((e.target as HTMLElement).closest('.resize-handle') === null) handleSort('activity'); }} title="Most recent local save or server sync">
            Last Activity {sortBy === 'activity' && <span style={{ marginLeft: 4 }}>{sortDir === 'asc' ? '▲' : '▼'}</span>} <span className="resize-handle" onMouseDown={startResize("activity")} />
          </div>
          <div className="col-header" style={{ justifyContent: "center" }} title="ROM source — 🌐 network · 💾 local copy">Src</div>
          <div className="col-header" style={{ justifyContent: "flex-end" }}>Actions</div>

          {(() => {
            const localGames = games.filter(g => g.isLocal);
            const otherGames = games.filter(g => !g.isLocal);

            function renderGameRow(g: GameRow, canPlay: boolean, keyPrefix = "") {
              return (
                <React.Fragment key={keyPrefix + g.slug}>
                  <div className="game-cell">
                    <input
                      type="checkbox"
                      checked={selectedSlugs.has(g.slug)}
                      onChange={() => toggleSelection(g.slug)}
                      style={{ cursor: "pointer" }}
                    />
                  </div>
                  <div className="game-cell game-cell-name">
                    {g.name}
                  </div>
                  <div className="game-cell game-cell-muted">
                    {g.locked && <span style={{ color: "var(--red)", marginRight: 6 }}>🔒</span>}
                    {(() => {
                      const save = g.lastSave || "";
                      const sync = g.lastPush || "";
                      const newer = save > sync ? save : sync;
                      if (!newer) return <span>Never synced</span>;
                      // Label whether the shown time is a local save or a server sync.
                      const kind = save > sync ? "saved" : "synced";
                      return <><RelTime iso={newer} /> <span style={{ opacity: 0.55, fontSize: 11 }}>{kind}</span></>;
                    })()}
                  </div>
                  <div className="game-cell" style={{ justifyContent: "center" }}>
                    {g.romSource === "network" && (
                      <span
                        title={g.hasLocalCopy
                          ? "Network ROM — local copy available for offline play"
                          : "Network ROM — played from the network share"}
                        style={{ opacity: 0.8 }}
                      >
                        {g.hasLocalCopy ? "💾" : "🌐"}
                      </span>
                    )}
                  </div>
                  <div className="game-cell game-cell-actions">
                    <button
                      className="btn btn-icon"
                      title={canPlay ? "Play" : "Set up to play on this device"}
                      disabled={g.locked}
                      onClick={() => {
                        if (g.locked) return;
                        if (canPlay) onPlay(g.slug, g.name);
                        else setNetPlayTarget({ slug: g.slug, name: g.name });
                      }}
                    >▶</button>
                    <button className="btn btn-icon" title="Settings, devices, history & run" onClick={() => openGameModal(g, canPlay)}>⚙</button>
                  </div>
                </React.Fragment>
              );
            }

            function renderConsoleGroups(list: GameRow[], keyPrefix: string, canPlay: boolean) {
              return groupByConsole(list, sortBy, sortDir).map(([key, consoleGames]) => {
                const colKey = keyPrefix + key;
                return (
                  <React.Fragment key={colKey}>
                    <div className="console-section-header" style={{ gridColumn: "1 / -1" }} onClick={() => toggleConsole(colKey)}>
                      <ConsoleCheckbox
                        games={consoleGames}
                        selectedSlugs={selectedSlugs}
                        onToggle={() => toggleConsoleSelection(consoleGames)}
                      />
                      <span>{collapsedConsoles.has(colKey) ? "▶" : "▼"}</span>
                      <span style={{ flex: 1 }}>{key}</span>
                      <span style={{ color: "var(--text-muted)", fontSize: 12 }}>{consoleGames.length} game{consoleGames.length !== 1 ? "s" : ""}</span>
                    </div>

                    {!collapsedConsoles.has(colKey) && sortGamesInConsole(consoleGames, sortBy, sortDir).map((g) => renderGameRow(g, canPlay))}
                  </React.Fragment>
                );
              });
            }

            // Last few games actually played on this device, newest first. We
            // proxy "played" by the most recent local save / server sync time —
            // playing a game writes its save and pushes it (issue #258).
            const recentlyPlayed = [...localGames]
              .filter(g => lastActivity(g))
              .sort((a, b) => lastActivity(b).localeCompare(lastActivity(a)))
              .slice(0, 3);

            const localCollapsed  = collapsedSections.has("local");
            const otherCollapsed  = collapsedSections.has("other");
            const toggleSection   = (key: string) => setCollapsedSections(prev => {
              const next = new Set(prev);
              next.has(key) ? next.delete(key) : next.add(key);
              return next;
            });

            const recentCollapsed = collapsedSections.has("recent");

            return (
              <>
                {/* ── Recently played ── */}
                {recentlyPlayed.length > 0 && (
                  <>
                    <div
                      className="device-section-header"
                      style={{ gridColumn: "1 / -1", cursor: "pointer" }}
                      onClick={() => toggleSection("recent")}
                    >
                      <span style={{ marginRight: 6, fontSize: 11 }}>{recentCollapsed ? "▶" : "▼"}</span>
                      🕹 Recently played
                    </div>
                    {!recentCollapsed && recentlyPlayed.map((g) => renderGameRow(g, true, "recent:"))}
                  </>
                )}

                {/* ── On this device ── */}
                <div
                  className="device-section-header"
                  style={{ gridColumn: "1 / -1", cursor: "pointer", marginTop: recentlyPlayed.length > 0 ? 8 : 0 }}
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
                      <button
                        className="btn btn-ghost"
                        style={{ fontSize: 11, padding: "2px 8px", marginLeft: "auto" }}
                        disabled={!!searchingSlug}
                        title="Search network drives for all these games and add any found to this device"
                        onClick={e => { e.stopPropagation(); searchAndImportAll(otherGames); }}
                      >
                        {searchingSlug === "bulk"
                          ? <><span className="spinner" style={{ width: 10, height: 10, marginRight: 4 }} />Searching…</>
                          : "Search network"}
                      </button>
                    </div>
                    {!otherCollapsed && renderConsoleGroups(otherGames, "other:", false)}
                  </>
                )}
              </>
            );
          })()}
        </div>
      )}

      {importOpen && (
        <ConsoleImport
          onClose={() => onImportOpenChange(false)}
          onImported={reload}
        />
      )}

      {gameModal && (
        <GameModal
          target={gameModal}
          onClose={() => setGameModal(null)}
          onChanged={() => reload(true)}
          onLaunch={onPlay}
        />
      )}

      {netPlayTarget && (
        <NetworkPlaySetup
          slug={netPlayTarget.slug}
          name={netPlayTarget.name}
          onClose={() => setNetPlayTarget(null)}
          onPlay={onPlay}
          onChanged={() => reload(true)}
        />
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
