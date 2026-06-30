import React, { useEffect, useState } from "react";
import { configure, configureDevice, health, gamesOverview, releaseLock } from "./api";
import { DeviceProvider } from "./DeviceContext";
import Setup from "./components/Setup";
import GameList from "./components/GameList";
import GameConfig from "./components/GameConfig";
import ServerStatusButton from "./components/ServerStatusButton";
import ConflictsButton from "./components/ConflictsButton";


type Screen =
  | { name: "loading" }
  | { name: "setup" }
  | { name: "games" }
  | { name: "config-new" };

export default function App(): React.ReactElement {
  const [screen, setScreen] = useState<Screen>({ name: "loading" });
  const [loadingMessage, setLoadingMessage] = useState("Loading…");
  const [isServer, setIsServer] = useState(false);
  const [gameListKey, setGameListKey] = useState(0);
  const [importOpen, setImportOpen] = useState(false);
  const [selectedGameCount, setSelectedGameCount] = useState(0);   // for the topbar bulk-delete button (issue #287)
  const [confirmBulkDelete, setConfirmBulkDelete] = useState(false);
  const [gameRunning, setGameRunning] = useState(false);
  const [gameIsExternal, setGameIsExternal] = useState(false);
  const [runningGameName, setRunningGameName] = useState<string | null>(null);
  const [runningGameSlug, setRunningGameSlug] = useState<string | null>(null);
  const [myDeviceId, setMyDeviceId] = useState<string | null>(null);

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
    if (screen.name !== "games" || !myDeviceId) return;
    async function checkLocks(): Promise<void> {
      if (await window.emusync.game.isRunning()) return; // already tracked via gameProcess
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
    const onExited = (): void => { setGameRunning(false); setGameIsExternal(false); setRunningGameName(null); };
    window.emusync.game.onExited(onExited);
    return () => window.emusync.game.offExited(onExited);
  }, []);

  useEffect(() => {
    async function init(): Promise<void> {
      // config.load() returns null when absent — no need for a separate exists() call.
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
        setLoadingMessage("Starting server…");
        await window.emusync.server.start();
        setLoadingMessage("Waiting for server…");
        for (let i = 0; i < 100; i++) {
          if (await health()) break;
          await new Promise<void>((r) => setTimeout(r, 100));
        }
      } else {
        // Client devices: start sync daemon to receive incoming ROM transfers
        window.emusync.daemon.start();
      }
      // Show games immediately; release stale locks in the background.
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
      setGameListKey((k) => k + 1);
    });
  }

  async function handlePlay(slug: string, name?: string): Promise<void> {
    // Quick play / Run tab: launch immediately (emusync run derives the command
    // server-side). The topbar then reflects the running game (issue #260).
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
        <span className="spinner" style={{ width: 32, height: 32 }} />
        <span style={{ color: "var(--muted, #888)", fontSize: 13 }}>{loadingMessage}</span>
      </div>
    );
  }

  if (screen.name === "setup") {
    return <Setup onDone={handleSetupDone} />;
  }

  return (
    <DeviceProvider>
    <div className="layout">
      <header className="topbar">
        <span className="topbar-title">EmuSync</span>
        {gameRunning && (
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginRight: 8 }}>
            <span style={{ color: "#4ade80", fontWeight: 600, fontSize: 13 }}>
              {gameIsExternal
                ? `● Playing ${runningGameName ?? "game"} on Steam`
                : `● ${runningGameName ?? "Game"} running`}
            </span>
            {!gameIsExternal && (
              <button className="btn btn-danger" onClick={handleStop}>
                ■ Stop
              </button>
            )}
          </div>
        )}
        <div style={{ display: "flex", gap: 8 }}>
          {screen.name === "games" && (
            <button className="btn btn-ghost" onClick={() => setImportOpen(true)}>Bulk import</button>
          )}
          {screen.name === "games" && selectedGameCount > 0 && (
            <button className="btn btn-danger" onClick={() => setConfirmBulkDelete(true)}>
              🗑 Delete {selectedGameCount}
            </button>
          )}
          <ConflictsButton />
          <ServerStatusButton isServer={isServer} onRepaired={handleRepaired} />
        </div>
      </header>

      <main className="content">
        {screen.name === "games" && (
          <GameList
            key={gameListKey}
            onAdd={() => setScreen({ name: "config-new" })}
            onPlay={handlePlay}
            importOpen={importOpen}
            onImportOpenChange={setImportOpen}
            onSelectedCountChange={setSelectedGameCount}
            confirmBulkDelete={confirmBulkDelete}
            onConfirmBulkDeleteChange={setConfirmBulkDelete}
          />
        )}

        {screen.name === "config-new" && (
          <GameConfig
            slug={null}
            onBack={() => setScreen({ name: "games" })}
            onSaved={() => setScreen({ name: "games" })}
          />
        )}
      </main>

    </div>
    </DeviceProvider>
  );
}
