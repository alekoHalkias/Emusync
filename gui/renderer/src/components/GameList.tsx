import React, { useCallback, useEffect, useRef, useState } from "react";
import { listGames, removeGame, getSaveMeta, getLock, pushGameSaves, type Game } from "../api";
import ConsoleImport from "./ConsoleImport";

type Props = {
  onAdd: () => void;
  onEdit: (game: Game) => void;
  onPlay: (slug: string, name: string) => void;
};

type GameRow = Game & {
  lastPush?: string;
  locked?: boolean;
  syncing?: boolean;
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

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const raw = await listGames();
      const enriched = await Promise.all(
        raw.map(async (g): Promise<GameRow> => {
          const [meta, lock] = await Promise.allSettled([getSaveMeta(g.slug), getLock(g.slug)]);
          return {
            ...g,
            lastPush: meta.status === "fulfilled" && meta.value ? meta.value.pushed_at.slice(0, 19) : undefined,
            locked: lock.status === "fulfilled" ? lock.value.locked : false,
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
          <button className="btn btn-ghost" onClick={() => setShowEmulatorImport(true)}>🕹️ Add console</button>
          <button className="btn btn-primary" onClick={onAdd}>+ Add game</button>
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
        <div className="game-list">
          {(() => {
            const grouped = games.reduce<Record<string, GameRow[]>>((acc, g) => {
              const key = g.console || "Other";
              (acc[key] ??= []).push(g);
              return acc;
            }, {});
            const consoleKeys = Object.keys(grouped).sort();

            return consoleKeys.map(key => (
              <React.Fragment key={key}>
                <div className="console-section-header" onClick={() => toggleConsole(key)}>
                  <ConsoleCheckbox
                    games={grouped[key]}
                    selectedSlugs={selectedSlugs}
                    onToggle={() => toggleConsoleSelection(key, grouped[key])}
                  />
                  <span>{collapsedConsoles.has(key) ? "▶" : "▼"}</span>
                  <span style={{ flex: 1 }}>{key}</span>
                  <span style={{ color: "var(--text-muted)", fontSize: 12 }}>{grouped[key].length} game{grouped[key].length !== 1 ? "s" : ""}</span>
                </div>
                {!collapsedConsoles.has(key) && grouped[key].map((g) => (
                  <div key={g.slug} className="game-row">
                    <input
                      type="checkbox"
                      checked={selectedSlugs.has(g.slug)}
                      onChange={() => toggleSelection(g.slug)}
                      style={{ marginRight: 8, cursor: "pointer" }}
                    />
                    <div className="game-row-header">
                      <div className="game-row-name">{g.name}</div>
                      <div className="game-row-divider">|</div>
                      <div className="game-row-console" style={{ color: "var(--text-muted)", minWidth: 35 }}>
                        {g.console || "—"}
                      </div>
                      <div className="game-row-divider">|</div>
                      <div className="game-row-sync">
                        {g.locked && <span style={{ color: "var(--red)", marginRight: 6 }}>🔒 In use</span>}
                        <span>{g.lastPush ? g.lastPush : "Never synced"}</span>
                      </div>
                    </div>
                    <div className="game-row-actions">
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
                  </div>
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
