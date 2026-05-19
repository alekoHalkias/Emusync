import React, { useEffect, useState } from "react";
import { configure } from "./api";
import Setup from "./components/Setup";
import GameList from "./components/GameList";
import GameConfig from "./components/GameConfig";
import StatusBadge from "./components/StatusBadge";

type Screen =
  | { name: "loading" }
  | { name: "setup" }
  | { name: "games" }
  | { name: "config-new" }
  | { name: "config-edit"; slug: string; gameName: string };

export default function App(): React.ReactElement {
  const [screen, setScreen] = useState<Screen>({ name: "loading" });

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

  // Stub: launching via GUI just shows a toast — real play happens through the CLI wrapper
  function handlePlay(slug: string): void {
    alert(
      `To launch ${slug}, add this to your Steam launch options:\n\n` +
        `emusync run --game ${slug} -- %command%\n\n` +
        `Or run it manually in a terminal.`,
    );
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
    </div>
  );
}
