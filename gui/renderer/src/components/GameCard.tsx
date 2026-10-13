import React, { useEffect, useRef, useState } from "react";
import type { GameRow } from "./game-list/types";
import { RelTime } from "../time";
import { PlayIcon } from "./icons";

// Mirrors the ArtType union in gui/electron/art.ts (issue #324).
type ArtType = "grid" | "hero" | "logo" | "icon" | "wide_grid";

type Props = {
  game: GameRow;
  consoleKey: string;
  consoleAccent: string;
  artType: ArtType;
  selected: boolean;
  inSteam?: boolean;
  onToggleSelect: () => void;
  onPlay: (slug: string, name: string) => void;
  onSettings: (game: GameRow) => void;
  onArtStatus?: (slug: string, hasArt: boolean) => void;
};

export default function GameCard({ game, consoleKey, consoleAccent, artType, selected, inSteam, onToggleSelect, onPlay, onSettings, onArtStatus }: Props): React.ReactElement {
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
      data-slug={game.slug}
      style={{ "--card-accent": consoleAccent, cursor: "pointer" } as React.CSSProperties}
      onClick={() => onSettings(game)}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSettings(game); } }}
      role="button"
      tabIndex={0}
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
          tabIndex={-1}
          checked={selected}
          onChange={onToggleSelect}
          onClick={(e) => e.stopPropagation()}
          title={selected ? "Deselect" : "Select for deletion"}
        />

        {/* Overlay badges */}
        <div className="game-card-badges">
          {inSteam && (
            <span className="game-card-badge game-card-badge-net" title="Added to Steam">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-label="Steam"><path d="M12 2a10 10 0 0 0-10 9.3l5.4 2.2a2.8 2.8 0 0 1 1.6-.5l2.4-3.5v-.1a3.8 3.8 0 1 1 3.8 3.8h-.1l-3.4 2.5a2.8 2.8 0 0 1-5.5.6L2.2 14.7A10 10 0 1 0 12 2zm-4.6 15.3 1.2.5a2.1 2.1 0 1 0 1.1-2.8l1.3.5a1.5 1.5 0 1 1-1.1 2.8l-1.2-.5zm9.4-6.6a2.5 2.5 0 1 0-5 0 2.5 2.5 0 0 0 5 0zm-4.4 0a1.9 1.9 0 1 1 3.8 0 1.9 1.9 0 0 1-3.8 0z"/></svg>
            </span>
          )}
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
          <PlayIcon />
        </button>
      </div>
    </div>
  );
}
