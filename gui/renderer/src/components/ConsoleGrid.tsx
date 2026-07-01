import React, { useEffect, useState } from "react";
import type { GameRow } from "./game-list/types";

// Visual identity per console key: accent color + emoji icon
const CONSOLE_STYLE: Record<string, { color: string; icon: string }> = {
  snes:      { color: "#7c3aed", icon: "🎮" },
  nes:       { color: "#dc2626", icon: "🎮" },
  n64:       { color: "#2563eb", icon: "🕹" },
  nds:       { color: "#0891b2", icon: "📺" },
  "3ds":     { color: "#0284c7", icon: "📺" },
  gba:       { color: "#8b5cf6", icon: "🎮" },
  gb:        { color: "#6b7280", icon: "🎮" },
  gbc:       { color: "#059669", icon: "🎮" },
  genesis:   { color: "#1d4ed8", icon: "🕹" },
  sms:       { color: "#1e40af", icon: "🕹" },
  pce:       { color: "#b45309", icon: "🕹" },
  psx:       { color: "#4b5563", icon: "🎮" },
  ps2:       { color: "#1e3a8a", icon: "🎮" },
  psp:       { color: "#0f172a", icon: "📟" },
  saturn:    { color: "#7f1d1d", icon: "🕹" },
  gg:        { color: "#064e3b", icon: "📟" },
  atari2600: { color: "#78350f", icon: "🕹" },
  lynx:      { color: "#92400e", icon: "📟" },
};

const DEFAULT_STYLE = { color: "#374151", icon: "🎮" };

export type ConsoleDef = { key: string; label: string; abbr: string };

type ConsoleCard = {
  key: string;
  label: string;
  abbr: string;
  totalGames: number;
  localGames: number;
};

type Props = {
  games: GameRow[];
  onSelectConsole: (consoleKey: string, consoleLabel: string, consoleAbbr: string) => void;
};

export default function ConsoleGrid({ games, onSelectConsole }: Props): React.ReactElement {
  const [consoleDefs, setConsoleDefs] = useState<ConsoleDef[]>([]);

  useEffect(() => {
    window.emusync.emulator.consoles()
      .then((list) => setConsoleDefs(list as ConsoleDef[]))
      .catch(() => {/* server offline — will show placeholder labels */});
  }, []);

  // Build abbr → def lookup. Falls back to treating the stored console value
  // as an abbr when no matching def is found (e.g. custom / unknown console).
  const abbrToDef = new Map<string, ConsoleDef>();
  for (const def of consoleDefs) {
    if (def.abbr) abbrToDef.set(def.abbr.toUpperCase(), def);
    abbrToDef.set(def.key.toUpperCase(), def);
    abbrToDef.set(def.label.toUpperCase(), def);
  }

  // Group games by console
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
        const style = CONSOLE_STYLE[c.key] ?? DEFAULT_STYLE;
        return (
          <button
            key={c.key}
            className="console-card"
            onClick={() => onSelectConsole(c.key, c.label, c.abbr)}
            style={{ "--console-accent": style.color } as React.CSSProperties}
          >
            <div className="console-card-icon">{style.icon}</div>
            <div className="console-card-abbr">{c.abbr}</div>
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
