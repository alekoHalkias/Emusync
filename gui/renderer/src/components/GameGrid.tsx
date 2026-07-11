import React, { useEffect, useState } from "react";
import { deleteGame } from "../gameDelete";
import type { GameRow } from "./game-list/types";
import type { GameModalTarget } from "./GameModal";
import GameCard from "./GameCard";
import GameFilterButton, { EMPTY_FILTERS, matchesFilters, type GameFilters } from "./GameFilterButton";
import GameModal from "./GameModal";
import NetworkPlaySetup from "./NetworkPlaySetup";
import SteamRestartModal from "./SteamRestartModal";
import DownloadProgressModal, { type DownloadModalState } from "./DownloadProgressModal";

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
  // Deleting the network master is independent of bulkRemoveEverywhere (#376)
  // and needs its own strong confirmation before it actually runs.
  const [bulkDeleteNetworkRom, setBulkDeleteNetworkRom] = useState(false);
  const [confirmBulkNetworkDelete, setConfirmBulkNetworkDelete] = useState(false);
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
  // Slugs with an EmuSync Steam shortcut (issue #391) — null until the batch
  // check resolves, so the Steam filter passes everything while loading.
  const [steamSlugs, setSteamSlugs] = useState<Set<string> | null>(null);
  const [steamBusy, setSteamBusy] = useState(false);
  // One shared dismissible result line under the header for every bulk action
  // (Add to Steam #391, Download #396) — they can't run concurrently anyway.
  const [bulkMsg, setBulkMsg] = useState<{ text: string; isError: boolean } | null>(null);
  // Steam-is-open confirm (issue #393): offer to close Steam, add, relaunch.
  const [showSteamRestart, setShowSteamRestart] = useState(false);
  // Bulk ROM download (issue #396): localize every selected network game.
  const [dlBusy, setDlBusy] = useState(false);
  const [dlModal, setDlModal] = useState<DownloadModalState | null>(null);
  const [dlCancelling, setDlCancelling] = useState(false);

  // hasArt is keyed only by slug, not by artType — a stale entry from the
  // previous type would otherwise keep a game wrongly filtered in/out of the
  // artwork filter forever, since a game the filter excludes never mounts
  // its GameCard to refresh the check for the new type (issue #345 follow-up).
  useEffect(() => { setHasArt({}); }, [artType]);

  useEffect(() => {
    window.emusync.steam.addedSlugs().then((slugs) => setSteamSlugs(new Set(slugs))).catch(() => {});
  }, []);

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
    if (bulkDeleteNetworkRom && !confirmBulkNetworkDelete) {
      setConfirmBulkNetworkDelete(true);
      return;
    }
    setDeleting(true);
    for (const slug of Array.from(selectedSlugs)) {
      try {
        await deleteGame(slug, {
          deleteLocalRom: bulkDeleteLocalRom,
          removeEverywhere: bulkRemoveEverywhere,
          deleteNetworkRom: bulkDeleteNetworkRom,
        });
      } catch { /* skip */ }
    }
    setSelectedSlugs(new Set());
    setConfirmDelete(false);
    setBulkDeleteLocalRom(false);
    setBulkRemoveEverywhere(false);
    setBulkDeleteNetworkRom(false);
    setConfirmBulkNetworkDelete(false);
    setDeleting(false);
    onChanged();
  }

  // Bulk "Download" (issue #396): localize every selected network-sourced
  // game via the existing rom:localize flow (free-space-checked, atomic,
  // updates server config). Local-source and already-localized games are
  // silently skipped; the first game of a console with no local folder
  // configured prompts the folder picker once (rom:localize persists the
  // choice onto the console, so the rest of the loop won't re-prompt).
  async function handleBulkDownload(): Promise<void> {
    setDlBusy(true);
    setBulkMsg(null);
    const selected = Array.from(selectedSlugs)
      .map((slug) => games.find((g) => g.slug === slug))
      .filter((g): g is GameRow => !!g);
    const targets = selected.filter((g) => g.romSource === "network" && !g.hasLocalCopy);
    const skipped = selected.length - targets.length;
    if (targets.length === 0) {
      setBulkMsg({ text: `Nothing to download — ${skipped} already local.`, isError: false });
      setDlBusy(false);
      return;
    }

    // Batch byte total for the modal's overall bar; a game whose master can't
    // be statted contributes 0 (its own localize will surface the real error).
    const sizes = await window.emusync.rom.localizeSizes(targets.map((g) => g.slug)).catch(() => ({} as Record<string, number>));
    const totalBytes = targets.reduce((sum, g) => sum + (sizes[g.slug] ?? 0), 0);

    // Overall progress = bytes of completed games + the current game's copied
    // bytes (from throttled main-process events). Speed is a light EMA over
    // >=500ms windows so it reads steady instead of jittering per chunk.
    let completedBytes = 0;
    let currentBase = 0;
    const speed = { lastT: Date.now(), lastBytes: 0, bps: 0 };
    const listener = window.emusync.rom.onLocalizeProgress(({ copied }) => {
      const doneBytes = currentBase + copied;
      const now = Date.now();
      const dt = now - speed.lastT;
      if (dt >= 500) {
        const inst = ((doneBytes - speed.lastBytes) / dt) * 1000;
        speed.bps = speed.bps > 0 ? speed.bps * 0.7 + inst * 0.3 : inst;
        speed.lastT = now;
        speed.lastBytes = doneBytes;
      }
      setDlModal((prev) => (prev ? { ...prev, doneBytes, speedBps: speed.bps } : prev));
    });

    let done = 0;
    let error: string | null = null;
    let cancelled = false;
    let pickedFolder: string | undefined;
    try {
      for (let i = 0; i < targets.length; i++) {
        const g = targets[i];
        currentBase = completedBytes;
        speed.lastT = Date.now();
        speed.lastBytes = completedBytes;
        setDlModal({ index: i + 1, count: targets.length, gameName: g.name, doneBytes: completedBytes, totalBytes, speedBps: speed.bps });
        try {
          let res = await window.emusync.rom.localize(g.slug, pickedFolder);
          if (!res.ok && !res.cancelled && res.error?.includes("No local destination")) {
            const folder = await window.emusync.dialog.openFolder();
            if (!folder) { error = "Cancelled — no download folder chosen."; break; }
            pickedFolder = folder;
            res = await window.emusync.rom.localize(g.slug, pickedFolder);
          }
          if (res.cancelled) { cancelled = true; break; }
          if (!res.ok) { error = res.error ?? "Download failed."; break; }
          completedBytes += sizes[g.slug] ?? 0;
          done++;
        } catch (e: unknown) {
          error = e instanceof Error ? e.message : "Download failed.";
          break;
        }
      }
    } finally {
      window.emusync.rom.offLocalizeProgress(listener);
    }
    if (cancelled) {
      setBulkMsg({ text: `Download cancelled — ${done} of ${targets.length} completed.`, isError: false });
    } else if (error) {
      setBulkMsg({ text: done > 0 ? `Downloaded ${done}, then failed: ${error}` : error, isError: true });
    } else {
      setBulkMsg({
        text: `Downloaded ${done}${skipped > 0 ? `, skipped ${skipped} already local` : ""}.`,
        isError: false,
      });
      setSelectedSlugs(new Set());
    }
    setDlModal(null);
    setDlCancelling(false);
    setDlBusy(false);
    onChanged();
  }

  async function cancelBulkDownload(): Promise<void> {
    setDlCancelling(true);
    await window.emusync.rom.cancelLocalize().catch(() => {});
  }

  // Bulk "Add to Steam" (issue #391): adds every selected game, silently
  // skipping ones that already have a shortcut. Any error aborts the loop and
  // is surfaced once for the whole batch. If Steam is running, offer to
  // restart it around the adds instead of refusing (#393).
  async function handleBulkAddToSteam(): Promise<void> {
    if (await window.emusync.steam.isRunning().catch(() => false)) {
      setShowSteamRestart(true);
      return;
    }
    await doBulkAddToSteam(false);
  }

  async function doBulkAddToSteam(relaunching: boolean): Promise<void> {
    setSteamBusy(true);
    setBulkMsg(null);
    const consoles = (await window.emusync.emulator.consoles().catch(() => [])) ?? [];
    let added = 0;
    let skipped = 0;
    let error: string | null = null;
    for (const slug of Array.from(selectedSlugs)) {
      const g = games.find((x) => x.slug === slug);
      if (!g) continue;
      if (steamSlugs?.has(slug)) { skipped++; continue; }
      const def = consoles.find((c: { key: string; label: string; abbr: string }) => c.abbr === (g.console ?? ""));
      try {
        const res = await window.emusync.steam.addGame(slug, g.name, def?.label ?? g.console ?? "", def?.key ?? (g.console ?? "").toLowerCase());
        if (!res.ok) { error = res.error ?? "Failed to add to Steam."; break; }
        added++;
      } catch (e: unknown) {
        error = e instanceof Error ? e.message : "Failed to add to Steam.";
        break;
      }
    }
    // Refresh so the filter and future bulk runs see the new state.
    const slugs = await window.emusync.steam.addedSlugs().catch(() => null);
    if (slugs) setSteamSlugs(new Set(slugs));
    if (error) {
      setBulkMsg({ text: added > 0 ? `Added ${added}, then failed: ${error}` : error, isError: true });
    } else {
      const seeThem = relaunching ? "Steam is restarting." : `Restart Steam to see ${added === 1 ? "it" : "them"}.`;
      setBulkMsg({
        text: `Added ${added} to Steam${skipped > 0 ? `, skipped ${skipped} already added` : ""}. ${seeThem}`,
        isError: false,
      });
      setSelectedSlugs(new Set());
    }
    setSteamBusy(false);
  }

  async function restartSteamAndBulkAdd(): Promise<void> {
    setSteamBusy(true);
    const down = await window.emusync.steam.shutdown().catch(() => ({ ok: false, error: "Couldn't close Steam." }));
    if (!down.ok) {
      setBulkMsg({ text: down.error ?? "Couldn't close Steam.", isError: true });
      setSteamBusy(false);
      setShowSteamRestart(false);
      return;
    }
    await doBulkAddToSteam(true);
    const up = await window.emusync.steam.launch().catch(() => ({ ok: false, error: "Couldn't relaunch Steam." }));
    if (!up.ok) setBulkMsg({ text: `Added, but Steam didn't relaunch: ${up.error ?? "unknown error"}`, isError: false });
    setShowSteamRestart(false);
  }

  const accent = CONSOLE_ACCENT[consoleKey] ?? DEFAULT_ACCENT;

  const searched = search.trim()
    ? games.filter((g) => g.name.toLowerCase().includes(search.trim().toLowerCase()))
    : games;
  const filtered = searched.filter((g) =>
    matchesFilters(
      filters,
      !!g.lastSave,
      g.romSource !== "network" || !!g.hasLocalCopy,
      hasArt[g.slug],
      steamSlugs === null ? undefined : steamSlugs.has(g.slug),
    )
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
        <div className="game-grid-select-wrap">
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
        </div>
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
          className="btn btn-ghost game-grid-header-btn"
          disabled={selectedSlugs.size === 0 || dlBusy}
          onClick={handleBulkDownload}
          title="Download the selected games' ROMs to this device (already-local games are skipped)"
        >
          {dlBusy
            ? <><span className="spinner" /> Downloading…</>
            : `⬇ Download${selectedSlugs.size > 0 ? ` ${selectedSlugs.size}` : ""}`}
        </button>
        <button
          className="btn btn-ghost game-grid-header-btn"
          disabled={selectedSlugs.size === 0 || steamBusy}
          onClick={handleBulkAddToSteam}
          title="Add the selected games to Steam (already-added games are skipped)"
        >
          {steamBusy ? <><span className="spinner" /> Adding…</> : `🎮 Add to Steam${selectedSlugs.size > 0 ? ` ${selectedSlugs.size}` : ""}`}
        </button>
        <button
          className="btn btn-danger game-grid-header-btn"
          disabled={selectedSlugs.size === 0}
          onClick={() => setConfirmDelete(true)}
        >
          🗑 Delete{selectedSlugs.size > 0 ? ` ${selectedSlugs.size}` : ""}
        </button>
      </div>

      {bulkMsg && (
        <div
          style={{ fontSize: 12, padding: "4px 16px", color: bulkMsg.isError ? "var(--color-danger, #e5484d)" : "var(--text-muted)", cursor: "pointer" }}
          onClick={() => setBulkMsg(null)}
          title="Dismiss"
        >
          {bulkMsg.text}
        </div>
      )}

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

      {dlModal && (
        <DownloadProgressModal
          state={dlModal}
          cancelling={dlCancelling}
          onCancel={cancelBulkDownload}
        />
      )}

      {showSteamRestart && (
        <SteamRestartModal
          count={selectedSlugs.size}
          busy={steamBusy}
          onYes={restartSteamAndBulkAdd}
          onNo={() => setShowSteamRestart(false)}
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

      {confirmDelete && confirmBulkNetworkDelete && (
        <div className="modal-overlay" onClick={() => !deleting && setConfirmBulkNetworkDelete(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3 style={{ color: "var(--color-danger, #e5484d)" }}>⚠ Delete network ROM files?</h3>
            <p>
              This will permanently delete the network-drive ROM file for {selectedSlugs.size} selected
              game{selectedSlugs.size !== 1 ? "s" : ""} (any that are network-sourced). <strong>This cannot be undone.</strong>
            </p>
            <div className="modal-actions">
              <button
                className="btn btn-ghost"
                onClick={() => { setConfirmBulkNetworkDelete(false); setBulkDeleteNetworkRom(false); }}
                disabled={deleting}
              >
                Cancel
              </button>
              <button className="btn btn-danger" onClick={handleBulkDelete} disabled={deleting}>
                {deleting ? <><span className="spinner" /> Deleting…</> : "Yes, delete the network ROM"}
              </button>
            </div>
          </div>
        </div>
      )}

      {confirmDelete && !confirmBulkNetworkDelete && (
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
              Also remove from all devices
            </label>
            {bulkRemoveEverywhere && (
              <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, marginBottom: 8, marginLeft: 20 }}>
                <input type="checkbox" checked={bulkDeleteNetworkRom} onChange={(e) => setBulkDeleteNetworkRom(e.target.checked)} disabled={deleting} />
                Also delete the ROM from the network drive
              </label>
            )}
            <div className="modal-actions">
              <button
                className="btn btn-ghost"
                onClick={() => {
                  setConfirmDelete(false);
                  setBulkDeleteLocalRom(false);
                  setBulkRemoveEverywhere(false);
                  setBulkDeleteNetworkRom(false);
                }}
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
