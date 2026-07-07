// Per-game Artwork tab (issue #325): search SteamGridDB, see the 4 current
// per-type images, and pick/replace/remove any of them via a picker modal.
// Complements the automatic per-console fetch in art.ts/GameCard.
import React, { useEffect, useState } from "react";
import { getGame, setGameSgdbId } from "../api";

type ArtType = "grid" | "hero" | "logo" | "icon" | "wide_grid";
const ART_TYPES: ArtType[] = ["grid", "wide_grid", "hero", "logo", "icon"];
const ART_TYPE_LABELS: Record<ArtType, string> = {
  grid: "Grid", wide_grid: "Wide", hero: "Hero", logo: "Logo", icon: "Icon",
};
const EMPTY_CURRENT: Record<ArtType, string | null> = { grid: null, wide_grid: null, hero: null, logo: null, icon: null };

type SgdbGameResult = { id: number; name: string; release_date: number; verified: boolean };
type SgdbCandidate = { id: number; thumb: string; url: string };

type Props = {
  slug: string;
  name: string;
  gameConsole: string;
};

export default function ArtworkTab({ slug, name, gameConsole }: Props): React.ReactElement {
  // Every seeded console's abbr lowercases to its key (verified across
  // cli/consoles_data.py) — reuse that instead of threading a separate
  // consoleKey prop through GameModal/GameGrid just for this tab.
  const consoleKey = gameConsole.toLowerCase();

  const [searchTerm, setSearchTerm] = useState(name);
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<SgdbGameResult[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [current, setCurrent] = useState<Record<ArtType, string | null>>(EMPTY_CURRENT);
  const [pickerType, setPickerType] = useState<ArtType | null>(null);
  const [candidates, setCandidates] = useState<SgdbCandidate[]>([]);
  const [loadingCandidates, setLoadingCandidates] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getGame(slug).then((g) => { if (g.sgdb_game_id) setSelectedId(g.sgdb_game_id); }).catch(() => {});
    window.emusync.artwork.getCurrent(slug, consoleKey).then(setCurrent).catch(() => {});
  }, [slug, consoleKey]);

  async function search(): Promise<void> {
    if (!searchTerm.trim()) return;
    setSearching(true);
    setError("");
    try {
      setResults(await window.emusync.artwork.searchGames(searchTerm.trim()));
    } finally {
      setSearching(false);
    }
  }

  async function doRefreshAll(sgdbGameId: number | null): Promise<void> {
    setRefreshing(true);
    setError("");
    try {
      await window.emusync.artwork.refreshAll(slug, name, consoleKey, sgdbGameId);
      await refreshCurrent();
    } finally {
      setRefreshing(false);
    }
  }

  async function pickGame(id: number): Promise<void> {
    setSelectedId(id);
    try { await setGameSgdbId(slug, id); } catch { /* best-effort — local selection still works this session */ }
    // Pull the id directly rather than through selectedId's state — a
    // just-clicked setSelectedId hasn't re-rendered yet, so reading the
    // state var here would still see the previous selection.
    await doRefreshAll(id);
  }

  async function openPicker(type: ArtType): Promise<void> {
    if (!selectedId) {
      setError("Search and pick a SteamGridDB match first.");
      return;
    }
    setError("");
    setPickerType(type);
    setLoadingCandidates(true);
    try {
      setCandidates(await window.emusync.artwork.listCandidates(selectedId, type));
    } finally {
      setLoadingCandidates(false);
    }
  }

  async function refreshCurrent(): Promise<void> {
    setCurrent(await window.emusync.artwork.getCurrent(slug, consoleKey));
  }

  async function pickCandidate(url: string): Promise<void> {
    if (!pickerType) return;
    const result = await window.emusync.artwork.setArt(slug, consoleKey, pickerType, url);
    if (result.ok) {
      await refreshCurrent();
      setPickerType(null);
    } else {
      setError(result.error || "Failed to save artwork.");
    }
  }

  async function clearCurrent(): Promise<void> {
    if (!pickerType) return;
    await window.emusync.artwork.clearArt(slug, consoleKey, pickerType);
    await refreshCurrent();
    setPickerType(null);
  }

  return (
    <div>
      {/* Search row */}
      <div className="input-group" style={{ marginBottom: 12 }}>
        <label>Search SteamGridDB</label>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") search(); }}
            placeholder="Game name"
            style={{ flex: 1 }}
          />
          <button className="btn btn-ghost" onClick={search} disabled={searching || !searchTerm.trim()}>
            {searching ? <span className="spinner" /> : "Search"}
          </button>
        </div>
      </div>

      {/* Results list — ~4 rows visible, scrolls for more */}
      {results.length > 0 && (
        <div style={{ maxHeight: 128, overflowY: "auto", border: "1px solid var(--border)", borderRadius: "var(--radius)", marginBottom: 16 }}>
          {results.map((r) => (
            <div
              key={r.id}
              onClick={() => pickGame(r.id)}
              style={{
                padding: "4px 10px", cursor: "pointer", fontSize: 12, lineHeight: 1.5,
                background: selectedId === r.id ? "var(--surface2)" : "transparent",
                borderBottom: "1px solid var(--border)",
                display: "flex", justifyContent: "space-between", alignItems: "center",
              }}
            >
              <span>{r.name}{selectedId === r.id ? " ✓" : ""}</span>
              {r.release_date > 0 && (
                <span style={{ color: "var(--text-muted)", fontSize: 11 }}>
                  {new Date(r.release_date * 1000).getFullYear()}
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      {error && <p className="error-msg" style={{ marginBottom: 12 }}>{error}</p>}

      {/* Current artwork tiles */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
        <label style={{ fontSize: 12, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.5px" }}>
          Current artwork
        </label>
        <button className="btn btn-ghost" onClick={() => doRefreshAll(selectedId)} disabled={refreshing} style={{ fontSize: 12 }}>
          {refreshing ? <><span className="spinner" /> Refreshing…</> : "↻ Refresh all"}
        </button>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 10 }}>
        {ART_TYPES.map((type) => (
          <div key={type} onClick={() => openPicker(type)} style={{ cursor: "pointer", textAlign: "center" }}>
            <div
              style={{
                aspectRatio: type === "hero" ? "16 / 6" : type === "wide_grid" ? "460 / 215" : type === "grid" ? "3 / 4" : "1 / 1",
                background: "#0a0a0a",
                borderRadius: "var(--radius)",
                overflow: "hidden",
                border: "1px solid var(--border)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              {current[type] ? (
                <img src={current[type]!} alt={ART_TYPE_LABELS[type]} style={{ width: "100%", height: "100%", objectFit: "contain" }} />
              ) : (
                <span style={{ fontSize: 11, color: "var(--text-muted)" }}>Not set</span>
              )}
            </div>
            <div style={{ fontSize: 12, marginTop: 4 }}>{ART_TYPE_LABELS[type]}</div>
          </div>
        ))}
      </div>

      {/* Picker modal */}
      {pickerType && (
        <div className="modal-overlay" onClick={() => setPickerType(null)}>
          <div className="modal" style={{ width: 640, maxWidth: "90vw" }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <h3 style={{ margin: 0 }}>{ART_TYPE_LABELS[pickerType]} artwork</h3>
              <button className="btn btn-ghost" onClick={() => setPickerType(null)}>✕</button>
            </div>

            {current[pickerType] && (
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 6 }}>Currently saved</div>
                <div style={{ position: "relative", width: 140, display: "inline-block" }}>
                  <img
                    src={current[pickerType]!}
                    alt="Current"
                    style={{ width: "100%", borderRadius: "var(--radius)", border: "1px solid var(--border)", display: "block" }}
                  />
                  <button
                    onClick={clearCurrent}
                    title="Remove saved artwork"
                    style={{
                      position: "absolute", top: -6, right: -6, width: 22, height: 22, borderRadius: "50%",
                      background: "#dc2626", color: "#fff", border: "none", cursor: "pointer", fontSize: 13, lineHeight: 1,
                    }}
                  >
                    ✕
                  </button>
                </div>
              </div>
            )}

            <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>Pick a replacement</div>
            {loadingCandidates ? (
              <div style={{ textAlign: "center", padding: 30 }}><span className="spinner" /></div>
            ) : candidates.length === 0 ? (
              <p style={{ color: "var(--text-muted)", fontSize: 13 }}>No candidates found for this type.</p>
            ) : (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, maxHeight: 320, overflowY: "auto" }}>
                {candidates.map((c) => (
                  <img
                    key={c.id}
                    src={c.thumb}
                    onClick={() => pickCandidate(c.url)}
                    style={{ width: "100%", cursor: "pointer", borderRadius: "var(--radius)", border: "1px solid var(--border)", objectFit: "contain", background: "#0a0a0a" }}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
