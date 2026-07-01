import React, { useEffect, useRef, useState } from "react";
import type { GameRow } from "./game-list/types";

// Accent colour per console key (no more emoji — logo fetched from retroarch-assets)
const CONSOLE_COLOR: Record<string, string> = {
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
  psp:       "#334155",
  saturn:    "#7f1d1d",
  gg:        "#064e3b",
  atari2600: "#78350f",
  lynx:      "#92400e",
};

const DEFAULT_COLOR = "#374151";

export type ConsoleDef = { key: string; label: string; abbr: string };

type ConsoleCard = {
  key: string;
  label: string;
  abbr: string;
  totalGames: number;
  localGames: number;
};

/** Fetches the console logo once and renders it; shows the abbr text as fallback. */
function ConsoleIcon({ consoleKey, abbr }: { consoleKey: string; abbr: string }): React.ReactElement {
  const [iconUrl, setIconUrl] = useState<string | null>(null);
  const fetchedRef = useRef(false);

  useEffect(() => {
    if (fetchedRef.current) return;
    fetchedRef.current = true;
    window.emusync.art.getConsoleIcon(consoleKey)
      .then((url) => { if (url) setIconUrl(url); })
      .catch(() => {/* stay on text fallback */});
  }, [consoleKey]);

  if (iconUrl) {
    return (
      <img
        src={iconUrl}
        alt={abbr}
        className="console-card-logo"
      />
    );
  }

  // Fallback: styled abbr text while logo loads (or if unavailable)
  return <div className="console-card-abbr-fallback">{abbr}</div>;
}

type Props = {
  games: GameRow[];
  onSelectConsole: (consoleKey: string, consoleLabel: string, consoleAbbr: string) => void;
};

export default function ConsoleGrid({ games, onSelectConsole }: Props): React.ReactElement {
  const [consoleDefs, setConsoleDefs] = useState<ConsoleDef[]>([]);

  useEffect(() => {
    window.emusync.emulator.consoles()
      .then((list) => setConsoleDefs(list as ConsoleDef[]))
      .catch(() => {/* server offline */});
  }, []);

  const abbrToDef = new Map<string, ConsoleDef>();
  for (const def of consoleDefs) {
    if (def.abbr) abbrToDef.set(def.abbr.toUpperCase(), def);
    abbrToDef.set(def.key.toUpperCase(), def);
    abbrToDef.set(def.label.toUpperCase(), def);
  }

  const cardMap = new Map<string, ConsoleCard>();
  for (const g of games) {
    const stored = (g.console ?? "").toUpperCase();
    const def = abbrToDef.get(stored);
    const key   = def?.key   ?? stored.toLowerCase();
    const label = def?.label ?? g.console ?? key;
    const abbr  = def?.abbr  ?? (g.console ?? key.toUpperCase());

    if (!cardMap.has(key)) {
      cardMap.set(key, { key, label, abbr, totalGames: 0, localGames: 0 });
    }
    const card = cardMap.get(key)!;
    card.totalGames++;
    if (g.isLocal) card.localGames++;
  }

  const cards = Array.from(cardMap.values()).sort((a, b) => a.label.localeCompare(b.label));

  if (cards.length === 0) {
    return (
      <div className="empty-state">
        <div style={{ fontSize: 48, marginBottom: 16 }}>🎮</div>
        <h3>No consoles yet</h3>
        <p style={{ marginBottom: 20 }}>Import a console to see your library here.</p>
      </div>
    );
  }

  return (
    <div className="console-grid">
      {cards.map((c) => {
        const color = CONSOLE_COLOR[c.key] ?? DEFAULT_COLOR;
        return (
          <button
            key={c.key}
            className="console-card"
            onClick={() => onSelectConsole(c.key, c.label, c.abbr)}
            style={{ "--console-accent": color } as React.CSSProperties}
          >
            <div className="console-card-icon-wrap">
              <ConsoleIcon consoleKey={c.key} abbr={c.abbr} />
            </div>
            <div className="console-card-label">{c.label}</div>
            <div className="console-card-count">
              {c.localGames > 0 && c.localGames < c.totalGames
                ? `${c.localGames} / ${c.totalGames} game${c.totalGames !== 1 ? "s" : ""}`
                : `${c.totalGames} game${c.totalGames !== 1 ? "s" : ""}`}
            </div>
          </button>
        );
      })}
    </div>
  );
}
