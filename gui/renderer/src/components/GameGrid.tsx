import React, { useEffect, useState } from "react";
import { deleteGame } from "../gameDelete";
import type { GameRow } from "./game-list/types";
import type { GameModalTarget } from "./GameModal";
import GameCard from "./GameCard";
import GameFilterButton, { EMPTY_FILTERS, matchesFilters, type GameFilters } from "./GameFilterButton";
import GameModal from "./GameModal";
import NetworkPlaySetup from "./NetworkPlaySetup";

// Mirrors the ArtType union in gui/electron/art.ts (issue #324).
type ArtType = "grid" | "hero" | "logo" | "icon" | "wide_grid";
const ART_TYPE_LABELS: Record<ArtType, string> = {
  grid: "Grid", wide_grid: "Wide", hero: "Hero", logo: "Logo", icon: "Icon",
};

// Accent color per console key (mirrors ConsoleGrid)
const CONSOLE_ACCENT: Record<string, string> = {
  snes:      "#7c3aed",
  nes:       "#dc2626",
  n64:       "#2563eb",
  nds:       "#0891b2",
  "3ds":     "#0284c7",
  gba:       "#8b5cf6",
  gb:        "#6b7280",
  gbc:       "#059669",
  genesis:   "#1d4ed8",
  sms:       "#1e40af",
  pce:       "#b45309",
  psx:       "#4b5563",
  ps2:       "#1e3a8a",
  psp:       "#0f172a",
  saturn:    "#7f1d1d",
  gg:        "#064e3b",
  atari2600: "#78350f",
  lynx:      "#92400e",
};
const DEFAULT_ACCENT = "#374151";

type Props = {
  consoleKey: string;
  games: GameRow[];
  onPlay: (slug: string, name: string) => void;
  onChanged: () => void;
};

export default function GameGrid({ consoleKey, games, onPlay, onChanged }: Props): React.ReactElement {
  const [gameModal, setGameModal] = useState<GameModalTarget | null>(null);
  const [netPlayTarget, setNetPlayTarget] = useState<{ slug: string; name: string } | null>(null);
  const [search, setSearch] = useState("");
  const [selectedSlugs, setSelectedSlugs] = useState<Set<string>>(new Set());
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  // Tier 2/3 bulk-delete options (issue #343), applied uniformly to every
  // selected game — mirrors GameConfig.tsx's single-game delete confirm.
  const [bulkDeleteLocalRom, setBulkDeleteLocalRom] = useState(false);
  const [bulkRemoveEverywhere, setBulkRemoveEverywhere] = useState(false);
  const [artType, setArtType] = useState<ArtType>("grid");
  // Bumped per-slug when the settings modal closes, so that game's GameCard
  // remounts and re-fetches art (it may have just been edited in the
  // Artwork tab) without refetching every other card on the screen.
  const [artRefresh, setArtRefresh] = useState<Record<string, number>>({});
  // Lifted from each GameCard's own art:get fetch (issue #345) rather than a
  // duplicate lookup — undefined until that card resolves, so the "with/
  // without artwork" filter doesn't hide everything while cards are loading.
  const [hasArt, setHasArt] = useState<Record<string, boolean>>({});
  const [filters, setFilters] = useState<GameFilters>(EMPTY_FILTERS);

  // hasArt is keyed only by slug, not by artType — a stale entry from the
  // previous type would otherwise keep a game wrongly filtered in/out of the
  // artwork filter forever, since a game the filter excludes never mounts
  // its GameCard to refresh the check for the new type (issue #345 follow-up).
  useEffect(() => { setHasArt({}); }, [artType]);

  useEffect(() => {
    window.emusync.config.load().then((cfg) => {
      const byConsole = (cfg?.art_type_by_console as Record<string, string>) ?? {};
      const stored = byConsole[consoleKey];
      if (stored === "grid" || stored === "hero" || stored === "logo" || stored === "icon" || stored === "wide_grid") {
        setArtType(stored);
      } else {
        setArtType("grid");
      }
    });
  }, [consoleKey]);

  async function changeArtType(type: ArtType): Promise<void> {
    // Write the config BEFORE flipping local state — art.ts's getArtType()
    // reads the config file straight off disk on every art:get call, so if
    // the remount (triggered by setArtType below) fires before this save
    // lands, the newly-mounted GameCard would still read the old type and
    // return the previous type's already-cached file (issue #324 follow-up).
    const cfg = (await window.emusync.config.load()) ?? {};
    const byConsole = { ...((cfg.art_type_by_console as Record<string, string>) ?? {}), [consoleKey]: type };
    await window.emusync.config.save({ ...cfg, art_type_by_console: byConsole });
    setArtType(type);
  }

  function toggleSelect(slug: string): void {
    setSelectedSlugs((prev) => {
      const next = new Set(prev);
      next.has(slug) ? next.delete(slug) : next.add(slug);
      return next;
    });
  }

  // Selects/deselects every currently-visible game — i.e. after search and
  // the GameFilterButton filters, not the console's full game list.
  function toggleSelectAll(): void {
    setSelectedSlugs(allFilteredSelected ? new Set() : new Set(filtered.map((g) => g.slug)));
  }

  async function handleBulkDelete(): Promise<void> {
    setDeleting(true);
    for (const slug of Array.from(selectedSlugs)) {
      try {
        await deleteGame(slug, { deleteLocalRom: bulkDeleteLocalRom, removeEverywhere: bulkRemoveEverywhere });
      } catch { /* skip */ }
    }
    setSelectedSlugs(new Set());
    setConfirmDelete(false);
    setBulkDeleteLocalRom(false);
    setBulkRemoveEverywhere(false);
    setDeleting(false);
    onChanged();
  }

  const accent = CONSOLE_ACCENT[consoleKey] ?? DEFAULT_ACCENT;

  const searched = search.trim()
    ? games.filter((g) => g.name.toLowerCase().includes(search.trim().toLowerCase()))
    : games;
  const filtered = searched.filter((g) =>
    matchesFilters(filters, !!g.lastSave, g.romSource !== "network" || !!g.hasLocalCopy, hasArt[g.slug])
  );
  const allFilteredSelected = filtered.length > 0 && filtered.every((g) => selectedSlugs.has(g.slug));

  const local  = filtered.filter((g) => g.isLocal);
  const remote = filtered.filter((g) => !g.isLocal);

  function openSettings(g: GameRow): void {
    setGameModal({
      slug: g.slug,
      name: g.name,
      gameConsole: g.console ?? "",
      gameIsLocal: g.isLocal,
      savePath: g.savePath,
      statePath: g.statePath,
      canPlay: g.isLocal && !g.locked,
    });
  }

  function closeGameModal(): void {
    if (gameModal) {
      const slug = gameModal.slug;
      setArtRefresh((prev) => ({ ...prev, [slug]: (prev[slug] ?? 0) + 1 }));
    }
    setGameModal(null);
  }

  function handleArtStatus(slug: string, found: boolean): void {
    setHasArt((prev) => (prev[slug] === found ? prev : { ...prev, [slug]: found }));
  }

  function handlePlay(g: GameRow): void {
    if (!g.isLocal) {
      setNetPlayTarget({ slug: g.slug, name: g.name });
    } else {
      onPlay(g.slug, g.name);
    }
  }

  return (
    <>
      {/* Header */}
      <div className="game-grid-header" style={{ "--grid-accent": accent } as React.CSSProperties}>
        <input
          className="game-grid-search"
          type="text"
          placeholder="Search…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <GameFilterButton filters={filters} onChange={setFilters} />
        <select
          className="game-grid-art-type"
          value={artType}
          onChange={(e) => changeArtType(e.target.value as ArtType)}
          title="Artwork type"
        >
          {(Object.keys(ART_TYPE_LABELS) as ArtType[]).map((t) => (
            <option key={t} value={t}>{ART_TYPE_LABELS[t]}</option>
          ))}
        </select>
        <div style={{ flex: 1 }} />
        <button
          className="btn btn-ghost game-grid-header-btn"
          disabled={filtered.length === 0}
          onClick={toggleSelectAll}
          title={allFilteredSelected ? "Deselect all visible games" : "Select all visible games"}
        >
          {allFilteredSelected ? "☑ Deselect All" : "☐ Select All"}
        </button>
        <button
          className="btn btn-danger game-grid-header-btn"
          disabled={selectedSlugs.size === 0}
          onClick={() => setConfirmDelete(true)}
        >
          🗑 Delete{selectedSlugs.size > 0 ? ` ${selectedSlugs.size}` : ""}
        </button>
      </div>

      {filtered.length === 0 ? (
        <div className="empty-state" style={{ padding: "40px 20px" }}>
          <p>{search.trim() ? `No games match "${search}".` : "No games match the active filters."}</p>
        </div>
      ) : (
        <div className="game-grid-body">
          {local.length > 0 && (
            <>
              {remote.length > 0 && (
                <div className="game-grid-section-label">On this device</div>
              )}
              <div className="game-grid-cards">
                {local.map((g) => (
                  <GameCard
                    key={`${g.slug}:${artType}:${artRefresh[g.slug] ?? 0}`}
                    game={g}
                    consoleKey={consoleKey}
                    consoleAccent={accent}
                    artType={artType}
                    selected={selectedSlugs.has(g.slug)}
                    onToggleSelect={() => toggleSelect(g.slug)}
                    onPlay={() => handlePlay(g)}
                    onSettings={() => openSettings(g)}
                    onArtStatus={handleArtStatus}
                  />
                ))}
              </div>
            </>
          )}

          {remote.length > 0 && (
            <>
              <div className="game-grid-section-label" style={{ marginTop: local.length > 0 ? 24 : 0 }}>
                On other devices
              </div>
              <div className="game-grid-cards">
                {remote.map((g) => (
                  <GameCard
                    key={`${g.slug}:${artType}:${artRefresh[g.slug] ?? 0}`}
                    game={g}
                    consoleKey={consoleKey}
                    consoleAccent={accent}
                    artType={artType}
                    selected={selectedSlugs.has(g.slug)}
                    onToggleSelect={() => toggleSelect(g.slug)}
                    onPlay={() => handlePlay(g)}
                    onSettings={() => openSettings(g)}
                    onArtStatus={handleArtStatus}
                  />
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {gameModal && (
        <GameModal
          target={gameModal}
          onClose={closeGameModal}
          onChanged={() => { closeGameModal(); onChanged(); }}
          onLaunch={onPlay}
        />
      )}

      {netPlayTarget && (
        <NetworkPlaySetup
          slug={netPlayTarget.slug}
          name={netPlayTarget.name}
          onClose={() => setNetPlayTarget(null)}
          onPlay={onPlay}
          onChanged={onChanged}
        />
      )}

      {confirmDelete && (
        <div className="modal-overlay" onClick={() => !deleting && setConfirmDelete(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Remove {selectedSlugs.size} game{selectedSlugs.size !== 1 ? "s" : ""} from this device?</h3>
            <p>This unlinks the selected games from this device. Save files and other devices' configs are <strong>not</strong> touched unless selected below.</p>
            <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, marginBottom: 8 }}>
              <input type="checkbox" checked={bulkDeleteLocalRom} onChange={(e) => setBulkDeleteLocalRom(e.target.checked)} disabled={deleting} />
              Also delete the ROM from local folders
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, marginBottom: 8 }}>
              <input type="checkbox" checked={bulkRemoveEverywhere} onChange={(e) => setBulkRemoveEverywhere(e.target.checked)} disabled={deleting} />
              Also remove from all devices and delete the network ROM
            </label>
            <div className="modal-actions">
              <button
                className="btn btn-ghost"
                onClick={() => { setConfirmDelete(false); setBulkDeleteLocalRom(false); setBulkRemoveEverywhere(false); }}
                disabled={deleting}
              >
                Cancel
              </button>
              <button className="btn btn-danger" onClick={handleBulkDelete} disabled={deleting}>
                {deleting ? <><span className="spinner" /> Deleting…</> : "Yes, delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
