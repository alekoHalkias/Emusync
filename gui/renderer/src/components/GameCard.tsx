import React, { useEffect, useRef, useState } from "react";
import type { GameRow } from "./game-list/types";
import { RelTime } from "../time";

// Mirrors the ArtType union in gui/electron/art.ts (issue #324).
type ArtType = "grid" | "hero" | "logo" | "icon" | "wide_grid";

type Props = {
  game: GameRow;
  consoleKey: string;
  consoleAccent: string;
  artType: ArtType;
  selected: boolean;
  onToggleSelect: () => void;
  onPlay: (slug: string, name: string) => void;
  onSettings: (game: GameRow) => void;
  onArtStatus?: (slug: string, hasArt: boolean) => void;
};

export default function GameCard({ game, consoleKey, consoleAccent, artType, selected, onToggleSelect, onPlay, onSettings, onArtStatus }: Props): React.ReactElement {
  const [artUrl, setArtUrl] = useState<string | null>(null);
  const [artFailed, setArtFailed] = useState(false);
  const fetchedRef = useRef(false);

  useEffect(() => {
    if (fetchedRef.current) return;
    fetchedRef.current = true;
    window.emusync.art.get(game.slug, game.name, consoleKey).then((url) => {
      if (url) setArtUrl(url);
      else setArtFailed(true);
      onArtStatus?.(game.slug, !!url);
    }).catch(() => { setArtFailed(true); onArtStatus?.(game.slug, false); });
  }, [game.slug, game.name, consoleKey]);

  const canPlay = game.isLocal && !game.locked;
  const lastActivity = game.lastSave ?? game.lastPush ?? null;

  return (
    <div
      className={`game-card${selected ? " game-card-selected" : ""}`}
      style={{ "--card-accent": consoleAccent, cursor: "pointer" } as React.CSSProperties}
      onClick={() => onSettings(game)}
      title="Settings, history & devices"
    >
      {/* Art area */}
      <div className={`game-card-art game-card-art-${artType}`}>
        {artUrl && !artFailed ? (
          <img
            src={artUrl}
            alt={game.name}
            className="game-card-img"
            onError={() => { setArtFailed(true); setArtUrl(null); }}
          />
        ) : (
          <div className="game-card-placeholder">
            <span className="game-card-placeholder-text">{game.name}</span>
          </div>
        )}

        {/* Selection checkbox — top-right corner */}
        <input
          type="checkbox"
          className="game-card-checkbox"
          checked={selected}
          onChange={onToggleSelect}
          onClick={(e) => e.stopPropagation()}
          title={selected ? "Deselect" : "Select for deletion"}
        />

        {/* Overlay badges */}
        <div className="game-card-badges">
          {game.locked && (
            <span className="game-card-badge game-card-badge-locked" title="Currently running on another device">
              🔒
            </span>
          )}
          {game.offline && (
            <span className="game-card-badge game-card-badge-offline" title="Server unreachable — showing cached data; save will sync once reconnected">
              ⚡ offline
            </span>
          )}
          {!game.isLocal && (
            <span className="game-card-badge game-card-badge-other" title="Not set up on this device">
              other device
            </span>
          )}
          {game.romSource === "network" && (
            <span
              className="game-card-badge game-card-badge-net"
              title={game.hasLocalCopy ? "Network ROM — local copy available" : "Network ROM"}
            >
              {game.hasLocalCopy ? "💾" : "🌐"}
            </span>
          )}
        </div>
      </div>

      {/* Info row */}
      <div className="game-card-info">
        <div className="game-card-name" title={game.name}>{game.name}</div>
        {lastActivity && (
          <div className="game-card-time">
            <RelTime iso={lastActivity} />
          </div>
        )}
      </div>

      {/* Action buttons */}
      <div className="game-card-actions">
        <button
          className="game-card-btn game-card-btn-play"
          title={canPlay ? "Play" : game.locked ? "Locked — running elsewhere" : "Not set up on this device"}
          disabled={game.locked || !game.isLocal}
          onClick={(e) => { e.stopPropagation(); if (canPlay) onPlay(game.slug, game.name); }}
        >
          ▶
        </button>
      </div>
    </div>
  );
}
