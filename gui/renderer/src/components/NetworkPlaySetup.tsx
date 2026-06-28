import React, { useEffect, useRef, useState } from "react";
import {
  createPullRequest,
  getDeviceConsoles,
  getGame,
  getGameNetworkSource,
  listGameDevices,
  setGameDevice,
  whoami,
  type DeviceForGame,
  type GameNetworkSource,
} from "../api";
import ConsoleImport from "./ConsoleImport";

type Props = {
  slug: string;
  name: string;
  onClose: () => void;
  onPlay: (slug: string, name: string) => void;
  onChanged: () => void;
};

function basename(p: string): string {
  return p.replace(/\\/g, "/").split("/").filter(Boolean).pop() || p;
}

/**
 * Play-time setup for a game that isn't configured on this device (issue #270).
 *
 * On open, immediately tries to find and import the game automatically:
 *   1. If this device has a recent import folder for the console, scan it silently.
 *   2. If found, import + launch with no user interaction needed.
 *   3. If not found or console not configured, show options modal.
 */
export default function NetworkPlaySetup({ slug, name, onClose, onPlay, onChanged }: Props): React.ReactElement {
  const [sources, setSources] = useState<DeviceForGame[]>([]);
  // "auto"   = trying to find + import automatically (show spinner only)
  // "manual" = auto-scan failed or console not configured, show options
  const [mode, setMode] = useState<"auto" | "manual">("auto");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [showConsoleImport, setShowConsoleImport] = useState(false);
  const [consoleKey, setConsoleKey] = useState<string | null>(null);
  const [networkMount, setNetworkMount] = useState<string | null>(null);
  const [gameNetworkSource, setGameNetworkSource] = useState<GameNetworkSource | null>(null);
  const autoAttempted = useRef(false);

  useEffect(() => {
    (async () => {
      try {
        const [devs, game, netSource] = await Promise.all([
          listGameDevices(slug).catch(() => [] as DeviceForGame[]),
          getGame(slug).catch(() => null),
          getGameNetworkSource(slug).catch(() => null),
        ]);
        setSources(devs.filter(d => d.rom_path));
        if (netSource) setGameNetworkSource(netSource);

        let foundKey: string | null = null;
        let foundMount: string | null = null;

        if (game) {
          const consoles = (await window.emusync.emulator.consoles().catch(() => [])) ?? [];
          const found = consoles.find(
            (c: { key: string; label: string; abbr?: string }) =>
              c.label === game.console || c.abbr === game.console || c.key === game.console,
          );
          if (found) {
            foundKey = found.key;
            setConsoleKey(found.key);
          }

          // Read this device's network mount for the console from local config
          if (foundKey) {
            try {
              const cfg = await window.emusync.config.load();
              const recentFolders = cfg?.recent_import_folders?.[foundKey];
              if (recentFolders && recentFolders.length > 0) {
                foundMount = recentFolders[0];
                setNetworkMount(recentFolders[0]);
              }
            } catch { /* no config */ }
          }
        }

        // Auto-scan: if we have a console key and a local network mount, try immediately
        if (foundKey && foundMount) {
          await tryAutoImport(foundKey, foundMount);
        } else {
          // No mount configured on this device — drop straight to manual options
          setMode("manual");
        }
      } catch (e) {
        console.error("NetworkPlaySetup failed to load game info:", e);
        setMode("manual");
      }
    })();
  }, [slug]);

  async function tryAutoImport(key: string, mount: string): Promise<void> {
    if (autoAttempted.current) return;
    autoAttempted.current = true;
    try {
      const { options: emulatorOptions } = await window.emusync.emulator.detect(key);
      if (!emulatorOptions || emulatorOptions.length === 0) {
        setMode("manual");
        return;
      }
      const emulator = emulatorOptions[0];
      const scanResult = await window.emusync.emulator.scan(key, emulator, [mount]);

      if (!scanResult?.roms || scanResult.roms.length === 0) {
        // Game not found on this device's network mount — show manual options
        setMode("manual");
        return;
      }

      const rom = scanResult.roms[0];
      if (!rom.romPath) { setMode("manual"); return; }

      await setGameDevice(slug, {
        rom_source: "network",
        rom_path: rom.romPath,
        save_path: rom.savePath,
        state_path: rom.statePath || "",
        launch_command: rom.launchCommand,
        rom_folder_path: mount,
      });
      onChanged();
      onClose();
      onPlay(slug, name);
    } catch {
      setMode("manual");
    }
  }

  async function setupAndPlaySilently(): Promise<void> {
    if (!consoleKey) return;
    setError(null);
    setBusy(true);
    try {
      const mount = networkMount;
      if (mount) {
        await tryAutoImport(consoleKey, mount);
        if (mode === "manual") setError(`Game not found on ${mount}`);
      } else if (gameNetworkSource && consoleKey) {
        setShowConsoleImport(true);
      } else {
        setError("Console not configured. Please set it up first.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function pullToDevice(): Promise<void> {
    setError(null); setStatus(null);
    setBusy(true);
    try {
      const source = sources[0];
      if (!source?.rom_path) { setError("No device has this ROM to pull from."); return; }

      const game = await getGame(slug);
      let folder = "";
      try {
        const { device_id } = await whoami();
        const consoles = await getDeviceConsoles(device_id);
        folder = consoles.find(c => c.console_name === game.console)?.device_game_folder || "";
      } catch { /* fall through to picker */ }
      if (!folder) {
        const picked = await window.emusync.dialog.openFolder();
        if (!picked) return;
        folder = picked;
      }

      const destination = `${folder.replace(/[/\\]$/, "")}/${basename(source.rom_path)}`;
      const res = await createPullRequest(slug, source.id, destination);
      setStatus(
        res.source_online
          ? `Requested from ${source.name}. It will arrive shortly (keep both devices' EmuSync running).`
          : `${source.name} is offline — the ROM will be delivered when it comes online.`,
      );
      onChanged();
    } catch (e: any) {
      setError(e.message || "Pull request failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ width: 520 }} onClick={(e) => e.stopPropagation()}>
        <h3>Play "{name}" on this device</h3>

        {mode === "auto" ? (
          // Auto-scanning — show a simple spinner, no options yet
          <div style={{ textAlign: "center", padding: "24px 0" }}>
            <span className="spinner" style={{ width: 24, height: 24 }} />
            <p style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 12 }}>
              Looking for this game on your network drive…
            </p>
          </div>
        ) : (
          <>
            <p style={{ fontSize: 13, color: "var(--text-muted)" }}>
              This game isn't set up on this device yet. Choose how to make it playable here:
            </p>

            {/* Option A — network drive */}
            <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 12, marginTop: 8 }}>
              <div style={{ fontWeight: 500, fontSize: 14 }}>🌐 Set up this console & play</div>
              <div style={{ fontSize: 12, color: "var(--text-muted)", margin: "4px 0 8px" }}>
                {networkMount
                  ? <>Search for this game on <code>{networkMount}</code> and play it.</>
                  : "Point this device at the network share for this console, then play."}
              </div>
              <button
                className="btn"
                disabled={!consoleKey || busy || (!networkMount && !gameNetworkSource)}
                onClick={(networkMount || gameNetworkSource) ? setupAndPlaySilently : () => setShowConsoleImport(true)}
              >
                {busy
                  ? <><span className="spinner" style={{ width: 12, height: 12, marginRight: 6 }} />Searching…</>
                  : (networkMount || gameNetworkSource ? "Search & play" : "Set up & play")}
              </button>
            </div>

            {/* Option B — pull to this device */}
            <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 12, marginTop: 8 }}>
              <div style={{ fontWeight: 500, fontSize: 14 }}>💾 Pull the ROM to this device</div>
              <div style={{ fontSize: 12, color: "var(--text-muted)", margin: "4px 0 8px" }}>
                {sources.length
                  ? <>Copy the ROM from <b>{sources[0].name}</b> onto this device for offline play.</>
                  : "No device currently has this ROM to pull from."}
              </div>
              <button
                className="btn btn-ghost"
                disabled={sources.length === 0 || busy}
                onClick={pullToDevice}
              >
                {busy
                  ? <><span className="spinner" style={{ width: 12, height: 12, marginRight: 6 }} />Requesting…</>
                  : "Pull ROM here"}
              </button>
            </div>

            {error && <p style={{ color: "var(--red)", fontSize: 12, marginTop: 12 }}>{error}</p>}
            {status && <p style={{ color: "var(--text-muted)", fontSize: 12, marginTop: 12 }}>{status}</p>}
          </>
        )}

        <div className="modal-actions">
          <button className="btn btn-ghost" onClick={onClose}>Close</button>
        </div>
      </div>

      {showConsoleImport && consoleKey && (
        <ConsoleImport
          initialConsole={consoleKey}
          onClose={() => setShowConsoleImport(false)}
          onImported={() => {
            setShowConsoleImport(false);
            onChanged();
            onClose();
            onPlay(slug, name);
          }}
        />
      )}
    </div>
  );
}
