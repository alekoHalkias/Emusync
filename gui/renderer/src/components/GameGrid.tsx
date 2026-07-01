import React, { useState } from "react";
import type { GameRow } from "./game-list/types";
import type { GameModalTarget } from "./GameModal";
import GameCard from "./GameCard";
import GameModal from "./GameModal";
import NetworkPlaySetup from "./NetworkPlaySetup";

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
  consoleLabel: string;
  consoleAbbr: string;
  games: GameRow[];
  onBack: () => void;
  onPlay: (slug: string, name: string) => void;
  onChanged: () => void;
};

export default function GameGrid({ consoleKey, consoleLabel, consoleAbbr, games, onBack, onPlay, onChanged }: Props): React.ReactElement {
  const [gameModal, setGameModal] = useState<GameModalTarget | null>(null);
  const [netPlayTarget, setNetPlayTarget] = useState<{ slug: string; name: string } | null>(null);
  const [search, setSearch] = useState("");

  const accent = CONSOLE_ACCENT[consoleKey] ?? DEFAULT_ACCENT;

  const filtered = search.trim()
    ? games.filter((g) => g.name.toLowerCase().includes(search.trim().toLowerCase()))
    : games;

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
        <button className="game-grid-back" onClick={onBack} title="Back to consoles">
          ‹ Back
        </button>
        <div className="game-grid-title">
          <span className="game-grid-abbr">{consoleAbbr}</span>
          <span className="game-grid-label">{consoleLabel}</span>
          <span className="game-grid-total">{games.length} game{games.length !== 1 ? "s" : ""}</span>
        </div>
        <input
          className="game-grid-search"
          type="text"
          placeholder="Search…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {filtered.length === 0 ? (
        <div className="empty-state" style={{ padding: "40px 20px" }}>
          <p>No games match "{search}".</p>
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
                    key={g.slug}
                    game={g}
                    consoleKey={consoleKey}
                    consoleAccent={accent}
                    onPlay={() => handlePlay(g)}
                    onSettings={() => openSettings(g)}
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
                    key={g.slug}
                    game={g}
                    consoleKey={consoleKey}
                    consoleAccent={accent}
                    onPlay={() => handlePlay(g)}
                    onSettings={() => openSettings(g)}
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
          onClose={() => setGameModal(null)}
          onChanged={() => { setGameModal(null); onChanged(); }}
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
    </>
  );
}
