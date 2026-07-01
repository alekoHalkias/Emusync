import React, { useEffect, useRef, useState } from "react";
import type { GameRow } from "./game-list/types";
import { RelTime } from "../time";

type Props = {
  game: GameRow;
  consoleKey: string;
  consoleAccent: string;
  onPlay: (slug: string, name: string) => void;
  onSettings: (game: GameRow) => void;
};

export default function GameCard({ game, consoleKey, consoleAccent, onPlay, onSettings }: Props): React.ReactElement {
  const [artUrl, setArtUrl] = useState<string | null>(null);
  const [artFailed, setArtFailed] = useState(false);
  const fetchedRef = useRef(false);

  useEffect(() => {
    if (fetchedRef.current) return;
    fetchedRef.current = true;
    window.emusync.art.get(game.slug, game.name, consoleKey).then((url) => {
      if (url) setArtUrl(url);
      else setArtFailed(true);
    }).catch(() => setArtFailed(true));
  }, [game.slug, game.name, consoleKey]);

  const canPlay = game.isLocal && !game.locked;
  const lastActivity = game.lastSave ?? game.lastPush ?? null;

  return (
    <div className="game-card" style={{ "--card-accent": consoleAccent } as React.CSSProperties}>
      {/* Art area */}
      <div className="game-card-art">
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

        {/* Overlay badges */}
        <div className="game-card-badges">
          {game.locked && (
            <span className="game-card-badge game-card-badge-locked" title="Currently running on another device">
              🔒
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
        <button
          className="game-card-btn game-card-btn-settings"
          title="Settings, history & devices"
          onClick={(e) => { e.stopPropagation(); onSettings(game); }}
        >
          ⚙
        </button>
      </div>
    </div>
  );
}
