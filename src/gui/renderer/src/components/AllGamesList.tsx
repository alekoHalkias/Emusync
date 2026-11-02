import React, { useState } from "react";
import type { GameRow } from "./game-list/types";
import GameModal from "./GameModal";
import type { GameModalTarget } from "./GameModal";
import { GearIcon, PlayIcon } from "./icons";

type Props = {
  games: GameRow[];
  /** Resolves a stored game.console value to the console key used for art lookups. */
  consoleKeyFor: (g: GameRow) => string;
  onPlay: (slug: string, name: string) => void;
  onChanged: () => void;
};

/** Flat list of every game with a minimal menu: Play and Settings (#720). */
export default function AllGamesList({ games, consoleKeyFor, onPlay, onChanged }: Props): React.ReactElement | null {
  const [modal, setModal] = useState<GameModalTarget | null>(null);
  if (games.length === 0) return null;

  const sorted = [...games].sort((a, b) => a.name.localeCompare(b.name));

  function openSettings(g: GameRow): void {
    setModal({
      slug: g.slug,
      name: g.name,
      gameConsole: g.console ?? "",
      consoleKey: consoleKeyFor(g),
      gameIsLocal: g.isLocal,
      savePath: g.savePath,
      statePath: g.statePath,
      canPlay: g.isLocal && !g.locked,
    });
  }

  return (
    <section className="all-games">
      <div className="game-grid-section-label">All games</div>
      {sorted.map((g) => (
        <div key={g.slug} className="all-games-row">
          <span className="all-games-name">{g.name}</span>
          <span className="all-games-meta">{g.console ?? ""}{g.isLocal ? "" : " - other device"}</span>
          <button
            className="btn btn-ghost"
            disabled={!g.isLocal || !!g.locked}
            onClick={() => onPlay(g.slug, g.name)}
            aria-label={`Play ${g.name}`}
          >
            <PlayIcon />
          </button>
          <button
            className="btn btn-ghost"
            onClick={() => openSettings(g)}
            aria-label={`Settings for ${g.name}`}
          >
            <GearIcon />
          </button>
        </div>
      ))}
      {modal && (
        <GameModal
          target={modal}
          onClose={() => setModal(null)}
          onChanged={() => { setModal(null); onChanged(); }}
          onLaunch={onPlay}
        />
      )}
    </section>
  );
}
