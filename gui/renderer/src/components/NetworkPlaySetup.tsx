import React, { useEffect, useState } from "react";
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
  /** Called after a successful network-drive setup so the parent can launch. */
  onPlay: (slug: string, name: string) => void;
  /** Called after any change (setup / pull request) to refresh the game list. */
  onChanged: () => void;
};

function basename(p: string): string {
  return p.replace(/\\/g, "/").split("/").filter(Boolean).pop() || p;
}

/**
 * Play-time setup for a game that isn't configured on this device (issue #270).
 * Offers two ways to make it playable here:
 *   A. Run the console import wizard pre-seeded with this game's console, so the
 *      device can point at the same network share (or local copy) and play.
 *   B. Pull the ROM bytes from a device that has it (delivered by sync-daemon).
 */
export default function NetworkPlaySetup({ slug, name, onClose, onPlay, onChanged }: Props): React.ReactElement {
  const [sources, setSources] = useState<DeviceForGame[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [showConsoleImport, setShowConsoleImport] = useState(false);
  const [consoleKey, setConsoleKey] = useState<string | null>(null);
  const [networkMount, setNetworkMount] = useState<string | null>(null);
  const [gameConsole, setGameConsole] = useState<string | null>(null);
  const [gameNetworkSource, setGameNetworkSource] = useState<GameNetworkSource | null>(null);

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
        if (game) {
          setGameConsole(game.console);
          // Resolve the import-wizard console key from the game's stored console.
          const consoles = (await window.emusync.emulator.consoles().catch(() => [])) ?? [];
          const found = consoles.find(
            (c: { key: string; label: string; abbr?: string }) =>
              c.label === game.console || c.abbr === game.console || c.key === game.console,
          );
          if (found) setConsoleKey(found.key);

          // Check if this console is already configured on this device with a network mount
          try {
            const { device_id } = await whoami();
            const deviceConsoles = await getDeviceConsoles(device_id);
            const consoleConfig = deviceConsoles.find(c => c.console_name === game.console);
            // Try device_network_folder first (network ROM root), fall back to device_game_folder
            const mountPath = consoleConfig?.device_network_folder || consoleConfig?.device_game_folder;
            if (mountPath) {
              setNetworkMount(mountPath);
            }
          } catch { /* no console config yet */ }
        }
      } catch (e) {
        console.error("NetworkPlaySetup failed to load game info:", e);
      } finally {
        setLoading(false);
      }
    })();
  }, [slug]);

  async function setupAndPlaySilently(): Promise<void> {
    setError(null);
    setBusy(true);
    try {
      // If this device already has the console configured with a network mount, scan there
      if (networkMount && consoleKey) {
        const { options: emulatorOptions } = await window.emusync.emulator.detect(consoleKey);
        if (!emulatorOptions || emulatorOptions.length === 0) {
          setError("No emulator detected for this console");
          return;
        }

        const emulator = emulatorOptions[0];
        const scanResult = await window.emusync.emulator.scan(consoleKey, emulator, [networkMount]);

        if (!scanResult?.roms || scanResult.roms.length === 0) {
          setError(`Game not found on ${networkMount}`);
          return;
        }

        const rom = scanResult.roms[0];
        if (!rom.romPath) {
          setError("Could not determine ROM path");
          return;
        }

        const config = {
          rom_source: "network",
          rom_path: rom.romPath,
          save_path: rom.savePath,
          state_path: rom.statePath || "",
          launch_command: rom.launchCommand,
          rom_folder_path: networkMount,
        };

        await setGameDevice(slug, config);
        onChanged();
        onClose();
        onPlay(slug, name);
        return;
      }

      // If console not configured locally but game is on network from another device,
      // open the import wizard pre-seeded with the console so user can configure it
      if (gameNetworkSource && consoleKey) {
        setShowConsoleImport(true);
        return;
      }

      // Console not configured and no network source available
      setError("Console not configured. Please set it up first.");
    } catch (e: any) {
      setError(e.message || "Failed to set up game");
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

      // Destination: this device's configured ROM folder for the game's console,
      // else ask the user to pick one.
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
        <h3>Play “{name}” on this device</h3>
        {loading ? (
          <div style={{ textAlign: "center", padding: "16px 0" }}>
            <span className="spinner" style={{ width: 20, height: 20 }} />
          </div>
        ) : (
          <>
            <p style={{ fontSize: 13, color: "var(--text-muted)" }}>
              This game isn’t set up on this device yet. Choose how to make it playable here:
            </p>

            {/* Option A — set up via the console import wizard (network share or local) */}
            <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 12, marginTop: 8 }}>
              <div style={{ fontWeight: 500, fontSize: 14 }}>🌐 Set up this console & play</div>
              <div style={{ fontSize: 12, color: "var(--text-muted)", margin: "4px 0 8px" }}>
                {networkMount
                  ? <>Search for this game on <code>{networkMount}</code> and play it.</>
                  : gameNetworkSource?.rom_path
                  ? <>Search for this game on the network share (<code>{gameNetworkSource.rom_path}</code>) and play it.</>
                  : "Point this device at the network share (or a local copy) for this console, then play."}
              </div>
              <button
                className="btn"
                disabled={(!consoleKey || busy) || (!networkMount && !gameNetworkSource)}
                onClick={(networkMount || gameNetworkSource) ? setupAndPlaySilently : () => setShowConsoleImport(true)}
              >
                {busy ? <><span className="spinner" style={{ width: 12, height: 12, marginRight: 6 }} />Searching…</> : (networkMount || gameNetworkSource ? "Search & play" : "Set up & play")}
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
                {busy ? <><span className="spinner" style={{ width: 12, height: 12, marginRight: 6 }} />Requesting…</> : "Pull ROM here"}
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
