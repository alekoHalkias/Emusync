import React, { useEffect, useRef, useState } from "react";
import { configure, configureDevice, gamesOverview, releaseLock } from "./api";
import { DeviceProvider } from "./DeviceContext";
import Setup from "./components/Setup";
import GameConfig from "./components/GameConfig";
import ServerStatusButton from "./components/ServerStatusButton";
import ConflictsButton from "./components/ConflictsButton";
import ConsoleGrid from "./components/ConsoleGrid";
import GameGrid from "./components/GameGrid";
import ConsoleImport from "./components/ConsoleImport";
import { useGameList } from "./components/game-list/useGameList";

type Screen =
  | { name: "loading" }
  | { name: "setup" }
  | { name: "games" }
  | { name: "console"; key: string; label: string; abbr: string }
  | { name: "config-new" };

export default function App(): React.ReactElement {
  const [screen, setScreen] = useState<Screen>({ name: "loading" });
  const [isServer, setIsServer] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [gameRunning, setGameRunning] = useState(false);
  const [gameIsExternal, setGameIsExternal] = useState(false);
  const [runningGameName, setRunningGameName] = useState<string | null>(null);
  const [runningGameSlug, setRunningGameSlug] = useState<string | null>(null);
  const [myDeviceId, setMyDeviceId] = useState<string | null>(null);

  // Shared game list — data source for both ConsoleGrid and GameGrid.
  // Only active after setup is complete; the hook starts polling on mount.
  const { games, loading, reload } = useGameList();

  useEffect(() => {
    window.emusync.config.load().then((cfg) => {
      if (cfg?.device_id) setMyDeviceId(cfg.device_id as string);
    });
  }, []);

  async function releaseStaleLocks(deviceId: string): Promise<void> {
    try {
      const overview = await gamesOverview();
      for (const g of overview) {
        if (g.locked && g.lock_device_id === deviceId) {
          await releaseLock(g.slug);
        }
      }
    } catch { /* server offline */ }
  }

  // Poll for locks held by this device to detect games launched outside the app (e.g. Steam)
  useEffect(() => {
    const onGameScreen = screen.name === "games" || screen.name === "console";
    if (!onGameScreen || !myDeviceId) return;
    async function checkLocks(): Promise<void> {
      if (await window.emusync.game.isRunning()) return;
      const pidFileActive = await window.emusync.game.hasPidFile();
      try {
        const overview = await gamesOverview();
        const mine = overview.find((g) => g.locked && g.lock_device_id === myDeviceId);
        if (mine) {
          if (pidFileActive) {
            setGameRunning(true);
            setGameIsExternal(true);
            setRunningGameName(mine.name);
            setRunningGameSlug(mine.slug);
          } else {
            await releaseLock(mine.slug);
          }
          return;
        }
        setGameRunning(false);
        setGameIsExternal(false);
        setRunningGameName(null);
        setRunningGameSlug(null);
      } catch { /* server offline */ }
    }
    const id = setInterval(checkLocks, 3000);
    return () => clearInterval(id);
  }, [screen.name, myDeviceId]);

  useEffect(() => {
    window.emusync.game.isRunning().then(setGameRunning);
    const onExited = (): void => {
      setGameRunning(false);
      setGameIsExternal(false);
      setRunningGameName(null);
    };
    window.emusync.game.onExited(onExited);
    return () => window.emusync.game.offExited(onExited);
  }, []);

  // Mouse back/forward side buttons (issues #354/#356). Back mirrors the
  // topbar's "‹ Back" link (console -> games); forward re-enters whichever
  // console you most recently left, one level deep — there's no multi-page
  // history here, just games <-> console. Refs (not state) so the listener
  // is registered once instead of re-subscribing on every screen change.
  const screenRef = useRef(screen);
  const lastConsoleRef = useRef<Screen | null>(null);
  useEffect(() => {
    if (screenRef.current.name === "console") lastConsoleRef.current = screenRef.current;
    screenRef.current = screen;
  }, [screen]);
  useEffect(() => {
    function handleMouseNav(e: MouseEvent): void {
      if (e.button === 3 && screenRef.current.name === "console") {
        setScreen({ name: "games" });
      } else if (e.button === 4 && screenRef.current.name === "games" && lastConsoleRef.current) {
        setScreen(lastConsoleRef.current);
      }
    }
    window.addEventListener("mouseup", handleMouseNav);
    return () => window.removeEventListener("mouseup", handleMouseNav);
  }, []);

  useEffect(() => {
    async function init(): Promise<void> {
      const cfg = await window.emusync.config.load();
      if (!cfg) {
        setScreen({ name: "setup" });
        return;
      }
      const deviceId   = (cfg.device_id   as string) || "";
      const deviceName = (cfg.device_name as string) || "";
      configure(
        (cfg.server_host as string) || "localhost",
        (cfg.server_port as number) || 8765,
        (cfg.server_pin  as string) || "",
      );
      configureDevice(deviceId, deviceName);
      setIsServer(!!(cfg.is_server as boolean));
      if (cfg.is_server) {
        // Fire-and-forget: don't block the UI on Python startup. useGameList
        // retries every 1 s until the server is ready, then switches to 5 s polling.
        window.emusync.server.start();
      } else {
        window.emusync.daemon.start();
      }
      setScreen({ name: "games" });
      if (deviceId) releaseStaleLocks(deviceId);
    }
    init();
  }, []);

  function handleSetupDone(): void {
    window.emusync.config.load().then((cfg) => {
      if (!cfg) return;
      configure(
        (cfg.server_host as string) || "localhost",
        (cfg.server_port as number) || 8765,
        (cfg.server_pin  as string) || "",
      );
      configureDevice((cfg.device_id as string) || "", (cfg.device_name as string) || "");
      setIsServer(!!(cfg.is_server as boolean));
      if (!cfg.is_server) window.emusync.daemon.start();
      setScreen({ name: "games" });
    });
  }

  function handleRepaired(): void {
    window.emusync.config.load().then((cfg) => {
      if (!cfg) return;
      configure(
        (cfg.server_host as string) || "localhost",
        (cfg.server_port as number) || 8765,
        (cfg.server_pin  as string) || "",
      );
      configureDevice((cfg.device_id as string) || "", (cfg.device_name as string) || "");
      reload(true);
    });
  }

  async function handlePlay(slug: string, name?: string): Promise<void> {
    if (name) setRunningGameName(name);
    setRunningGameSlug(slug);
    await window.emusync.game.launch(slug);
    setGameRunning(true);
    setGameIsExternal(false);
  }

  async function handleStop(): Promise<void> {
    if (await window.emusync.game.isRunning()) {
      await window.emusync.game.stop();
    } else if (runningGameSlug) {
      await window.emusync.game.stopExternal();
    }
    setGameRunning(false);
    setRunningGameName(null);
    setRunningGameSlug(null);
  }

  if (screen.name === "loading") {
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100vh", gap: 16 }}>
        <div className="loading-logo">EmuSync</div>
        <span className="spinner" style={{ width: 32, height: 32 }} />
      </div>
    );
  }

  if (screen.name === "setup") {
    return <Setup onDone={handleSetupDone} />;
  }

  // Determine which games belong to the currently-selected console
  const consoleGames = screen.name === "console"
    ? games.filter((g) => {
        const stored = (g.console ?? "").toUpperCase();
        return stored === screen.abbr.toUpperCase() || stored === screen.key.toUpperCase();
      })
    : [];

  return (
    <DeviceProvider>
    <div className="layout">
      <header className="topbar">
        {/* Left: back breadcrumb or app title */}
        {screen.name === "console" ? (
          // Grouped in one flex item — .topbar uses justify-content:
          // space-between, so an ungrouped sibling here would drift toward
          // the middle instead of sitting next to the back button.
          <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
            <button
              className="topbar-back"
              onClick={() => setScreen({ name: "games" })}
            >
              ‹ Back
            </button>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8, minWidth: 0 }}>
              <span className="game-grid-abbr">{screen.abbr}</span>
              <span className="game-grid-label">{screen.label}</span>
              <span className="game-grid-total">
                {consoleGames.length} game{consoleGames.length !== 1 ? "s" : ""}
              </span>
            </div>
          </div>
        ) : (
          <span className="topbar-title">EmuSync</span>
        )}

        {/* Centre: running game indicator */}
        {gameRunning && (
          <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1, justifyContent: "center" }}>
            <span className="topbar-game-running">
              {gameIsExternal
                ? `● Playing ${runningGameName ?? "game"} on Steam`
                : `● ${runningGameName ?? "Game"} running`}
            </span>
            {!gameIsExternal && (
              <button className="btn btn-danger" onClick={handleStop}>■ Stop</button>
            )}
          </div>
        )}

        {/* Right: topbar actions */}
        <div style={{ display: "flex", gap: 8, marginLeft: "auto" }}>
          {(screen.name === "games" || screen.name === "console") && (
            <button className="btn btn-ghost" onClick={() => setImportOpen(true)}>
              + Import
            </button>
          )}
          <ConflictsButton />
          <ServerStatusButton isServer={isServer} onRepaired={handleRepaired} />
        </div>
      </header>

      <main className="content">
        {/* Console home: grid of console cards */}
        {screen.name === "games" && (
          loading ? (
            <div style={{ textAlign: "center", padding: 60 }}>
              <span className="spinner" style={{ width: 28, height: 28 }} />
            </div>
          ) : (
            <ConsoleGrid
              games={games}
              onSelectConsole={(key, label, abbr) =>
                setScreen({ name: "console", key, label, abbr })
              }
            />
          )
        )}

        {/* Per-console game grid */}
        {screen.name === "console" && (
          <GameGrid
            consoleKey={screen.key}
            games={consoleGames}
            onPlay={handlePlay}
            onChanged={() => reload(true)}
          />
        )}

        {/* Add game form */}
        {screen.name === "config-new" && (
          <GameConfig
            slug={null}
            onBack={() => setScreen({ name: "games" })}
            onSaved={() => { setScreen({ name: "games" }); reload(true); }}
          />
        )}
      </main>

      {/* Console import modal — accessible from anywhere via topbar button */}
      {importOpen && (
        <ConsoleImport
          onClose={() => setImportOpen(false)}
          onImported={() => reload(true)}
        />
      )}
    </div>
    </DeviceProvider>
  );
}
