import React, { useEffect, useState } from "react";
import { configure, configureDevice, getGameDevice, health, listGames, getLock, releaseLock } from "./api";
import { DeviceProvider } from "./DeviceContext";
import Setup from "./components/Setup";
import GameList from "./components/GameList";
import GameConfig from "./components/GameConfig";
import ServerStatusButton from "./components/ServerStatusButton";
import DevicesButton from "./components/DevicesButton";

function CopyBox({ text }: { text: string }): React.ReactElement {
  const [copied, setCopied] = useState(false);
  function copy(): void {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }
  return (
    <div style={{ display: "flex", gap: 8, alignItems: "flex-start", marginBottom: 16 }}>
      <div style={{
        flex: 1,
        background: "var(--surface-2, #0f1923)",
        borderRadius: 6,
        padding: "10px 14px",
        fontFamily: "monospace",
        fontSize: 13,
        userSelect: "text",
        WebkitUserSelect: "text",
        wordBreak: "break-all",
        border: "1px solid var(--border, rgba(255,255,255,0.1))",
      }}>
        {text}
      </div>
      <button className="btn btn-ghost" onClick={copy} style={{ whiteSpace: "nowrap", flexShrink: 0 }}>
        {copied ? "✓ Copied!" : "Copy"}
      </button>
    </div>
  );
}

function PlayModal({ slug, launchCommand, onClose, onLaunched }: {
  slug: string;
  launchCommand: string | null;
  onClose: () => void;
  onLaunched: () => void;
}): React.ReactElement {
  const [launching, setLaunching] = useState(false);
  const [launched, setLaunched] = useState(false);
  const [launcherPath, setLauncherPath] = useState("emusync");
  useEffect(() => { window.emusync.launcher.path().then(setLauncherPath); }, []);
  const steamCommand = `"${launcherPath}" run --game ${slug} -- %command%`;

  async function launchDirect(): Promise<void> {
    if (!launchCommand) return;
    setLaunching(true);
    await window.emusync.game.launch(slug, launchCommand);
    setLaunching(false);
    setLaunched(true);
    onLaunched();
    setTimeout(() => { setLaunched(false); onClose(); }, 1500);
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 520 }}>
        <h3 style={{ marginBottom: 20 }}>Play {slug}</h3>

        <p style={{ marginBottom: 8, fontWeight: 500 }}>Launch directly</p>
        {launchCommand ? (
          <>
            <CopyBox text={launchCommand} />
            <button
              className="btn btn-primary"
              style={{ width: "100%", marginBottom: 20 }}
              onClick={launchDirect}
              disabled={launching || launched}
            >
              {launched ? "✓ Launched!" : launching ? "Launching…" : "▶ Launch now"}
            </button>
          </>
        ) : (
          <p style={{ color: "var(--muted, #888)", fontSize: 13, marginBottom: 20 }}>
            No launch command configured. Edit this game and set a launch command first.
          </p>
        )}

        <p style={{ marginBottom: 8, fontWeight: 500 }}>Add to Steam</p>
        <p style={{ fontSize: 13, color: "var(--muted, #888)", marginBottom: 8 }}>
          Paste this into Steam → game properties → launch options:
        </p>
        <CopyBox text={steamCommand} />

        <div className="modal-actions">
          <button className="btn btn-ghost" onClick={onClose}>Close</button>
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
  const [loadingMessage, setLoadingMessage] = useState("Loading…");
  const [isServer, setIsServer] = useState(false);
  const [gameListKey, setGameListKey] = useState(0);
  const [playSlug, setPlaySlug] = useState<string | null>(null);
  const [playLaunchCommand, setPlayLaunchCommand] = useState<string | null>(null);
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
      const games = await listGames();
      for (const game of games) {
        const lock = await getLock(game.slug);
        if (lock.locked && lock.device_id === deviceId) {
          await releaseLock(game.slug);
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
        const games = await listGames();
        for (const game of games) {
          const lock = await getLock(game.slug);
          if (lock.locked && lock.device_id === myDeviceId) {
            if (pidFileActive) {
              setGameRunning(true);
              setGameIsExternal(true);
              setRunningGameName(game.name);
              setRunningGameSlug(game.slug);
            } else {
              await releaseLock(game.slug);
            }
            return;
          }
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

  function handlePlay(slug: string, name?: string): void {
    setPlayLaunchCommand(null);
    setPlaySlug(slug);
    if (name) setRunningGameName(name);
    getGameDevice(slug)
      .then((gd) => setPlayLaunchCommand(gd.launch_command || null))
      .catch(() => {});
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
          <DevicesButton />
          <ServerStatusButton isServer={isServer} onRepaired={handleRepaired} />
        </div>
      </header>

      <main className="content">
        {screen.name === "games" && (
          <GameList
            key={gameListKey}
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

      {playSlug && (
        <PlayModal
          slug={playSlug}
          launchCommand={playLaunchCommand}
          onClose={() => { setPlaySlug(null); setPlayLaunchCommand(null); }}
          onLaunched={() => { setGameRunning(true); setGameIsExternal(false); }}
        />
      )}

    </div>
    </DeviceProvider>
  );
}
