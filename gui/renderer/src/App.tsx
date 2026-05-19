import React, { useEffect, useState } from "react";
import { configure } from "./api";
import Setup from "./components/Setup";
import GameList from "./components/GameList";
import GameConfig from "./components/GameConfig";
import StatusBadge from "./components/StatusBadge";

function PlayModal({ slug, onClose }: { slug: string; onClose: () => void }): React.ReactElement {
  const [copied, setCopied] = useState(false);
  const command = `emusync run --game ${slug} -- %command%`;

  function copy(): void {
    navigator.clipboard.writeText(command).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>Launch {slug}</h3>
        <p style={{ marginBottom: 8 }}>Add this to your Steam launch options:</p>
        <div style={{
          background: "var(--surface-2, #0f1923)",
          borderRadius: 6,
          padding: "10px 14px",
          fontFamily: "monospace",
          fontSize: 13,
          userSelect: "text",
          WebkitUserSelect: "text",
          wordBreak: "break-all",
          marginBottom: 12,
          border: "1px solid var(--border, rgba(255,255,255,0.1))",
        }}>
          {command}
        </div>
        <div className="modal-actions">
          <button className="btn btn-ghost" onClick={onClose}>Close</button>
          <button className="btn btn-primary" onClick={copy}>
            {copied ? "✓ Copied!" : "Copy"}
          </button>
        </div>
      </div>
    </div>
  );
}

type Screen =
  | { name: "loading" }
  | { name: "setup" }
  | { name: "games" }
  | { name: "config-new" }
  | { name: "config-edit"; slug: string; gameName: string };

export default function App(): React.ReactElement {
  const [screen, setScreen] = useState<Screen>({ name: "loading" });
  const [playSlug, setPlaySlug] = useState<string | null>(null);

  useEffect(() => {
    async function init(): Promise<void> {
      const exists = await window.emusync.config.exists();
      if (!exists) {
        setScreen({ name: "setup" });
        return;
      }
      const cfg = await window.emusync.config.load();
      if (!cfg) {
        setScreen({ name: "setup" });
        return;
      }
      configure(
        (cfg.server_host as string) || "localhost",
        (cfg.server_port as number) || 8765,
        (cfg.token as string) || "",
      );
      setScreen({ name: "games" });
    }
    init();
  }, []);

  function handleSetupDone(): void {
    window.emusync.config.load().then((cfg) => {
      if (!cfg) return;
      configure(
        (cfg.server_host as string) || "localhost",
        (cfg.server_port as number) || 8765,
        (cfg.token as string) || "",
      );
      setScreen({ name: "games" });
    });
  }

  function handlePlay(slug: string): void {
    setPlaySlug(slug);
  }

  if (screen.name === "loading") {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh" }}>
        <span className="spinner" style={{ width: 32, height: 32 }} />
      </div>
    );
  }

  if (screen.name === "setup") {
    return <Setup onDone={handleSetupDone} />;
  }

  return (
    <div className="layout">
      <header className="topbar">
        <span className="topbar-title">EmuSync</span>
        <StatusBadge />
      </header>

      <main className="content">
        {screen.name === "games" && (
          <GameList
            onAdd={() => setScreen({ name: "config-new" })}
            onEdit={(g) => setScreen({ name: "config-edit", slug: g.slug, gameName: g.name })}
            onPlay={handlePlay}
          />
        )}

        {screen.name === "config-new" && (
          <GameConfig
            slug={null}
            onBack={() => setScreen({ name: "games" })}
            onSaved={() => setScreen({ name: "games" })}
          />
        )}

        {screen.name === "config-edit" && (
          <GameConfig
            slug={screen.slug}
            name={screen.gameName}
            onBack={() => setScreen({ name: "games" })}
            onSaved={() => setScreen({ name: "games" })}
            onPlay={handlePlay}
          />
        )}
      </main>

      {playSlug && <PlayModal slug={playSlug} onClose={() => setPlaySlug(null)} />}
    </div>
  );
}
