import React, { useCallback, useEffect, useState } from "react";
import { configure, configureDevice, health, listEvents, whoami, type ActivityEvent } from "../api";
import { RelTime } from "../time";
import DevicesPanel from "./DevicesPanel";
import SaveField from "./settings/SaveField";
import PinInput from "./settings/PinInput";
import { useDevices } from "../DeviceContext";
import { CloseIcon, DotIcon, PlayIcon, StopIcon, UploadIcon, WarningIcon } from "./icons";
import Modal from "./Modal";

type ServerState = "checking" | "online" | "offline";
type StartState = "idle" | "starting" | "running";

type DisplayState = { scale: number; fullscreen: boolean; autoUpdateEnabled: boolean };

export default function ServerStatusButton({ isServer, onRepaired, display, onDisplay }: {
  isServer: boolean;
  onRepaired: () => void;
  display: DisplayState;
  onDisplay: (d: Partial<DisplayState>) => void;
}): React.ReactElement {
  const { devices } = useDevices();
  const [serverState, setServerState] = useState<ServerState>("checking");
  const [open, setOpen] = useState(false);
  const [startState, setStartState] = useState<StartState>("idle");

  // PIN management
  const [pinInput, setPinInput] = useState("");
  const [pinConfirming, setPinConfirming] = useState(false);
  const [pinBusy, setPinBusy] = useState(false);
  const [pinError, setPinError] = useState("");

  // Device name
  const [deviceName, setDeviceName] = useState("");
  const [watchSaves, setWatchSaves] = useState(false);
  const [deviceId, setDeviceId] = useState("");
  const [dataDir, setDataDir] = useState("");
  const [clearConfirm, setClearConfirm] = useState(false);
  const [copied, setCopied] = useState(false);

  // Activity log
  const [showActivity, setShowActivity] = useState(false);
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [eventsLoading, setEventsLoading] = useState(false);

  // LAN discovery warning
  const [existingServers, setExistingServers] = useState<Array<{ name: string; host: string; port: number }>>([]);
  const [startWarningConfirmed, setStartWarningConfirmed] = useState(false);

  // SteamGridDB art key (issue #322)
  const [artKeyInput, setArtKeyInput] = useState("");

  // Connect-to-server form
  const [pairHost, setPairHost] = useState("");
  const [pairPort, setPairPort] = useState("8765");
  const [pairPin, setPairPin] = useState("");
  const [pairBusy, setPairBusy] = useState(false);
  const [pairError, setPairError] = useState("");
  const [pairSuccess, setPairSuccess] = useState(false);
  const [pairServerWarning, setPairServerWarning] = useState(false);

  const poll = useCallback(async () => {
    const ok = await health();
    setServerState(ok ? "online" : "offline");
    // Heartbeat: keeps this device's server-side presence fresh while the
    // GUI is open, so an idle-but-open app doesn't get logged as "went
    // offline" (issue #450). Best-effort — no-op before pairing / bad PIN.
    whoami().catch(() => {});
  }, []);

  useEffect(() => {
    poll();
    const id = setInterval(poll, 5000);
    return () => clearInterval(id);
  }, [poll]);

  useEffect(() => {
    if (!open || !showActivity) return;
    setEventsLoading(true);
    listEvents().then(setEvents).catch(() => setEvents([])).finally(() => setEventsLoading(false));
  }, [open, showActivity]);

  useEffect(() => {
    if (!open) return;
    window.emusync.config.load().then((cfg) => {
      if (!cfg) return;
      setPairHost((cfg.server_host as string) || "localhost");
      setPairPort(String((cfg.server_port as number) || 8765));
      setPairPin((cfg.server_pin as string) || "");
      setDeviceName((cfg.device_name as string) || "");
      setPinInput((cfg.server_pin as string) || "");
      setWatchSaves(!!cfg.watch_saves);
      setDeviceId((cfg.device_id as string) || "");
      setDataDir((cfg.data_dir as string) || "");
    });
    window.emusync.steamgriddb.getKey().then((key) => {
      setArtKeyInput(key || "");
    });
  }, [open]);

  async function handleStartServer(): Promise<void> {
    // Check for existing servers on LAN first
    if (!startWarningConfirmed) {
      const found = await window.emusync.server.discover();
      const others = found.filter((s) => s.host !== "127.0.0.1" && s.host !== "localhost");
      if (others.length > 0) {
        setExistingServers(others);
        return;
      }
    }
    setExistingServers([]);
    setStartWarningConfirmed(false);
    setStartState("starting");
    const result = await window.emusync.server.start();
    if (!result.ok) {
      setStartState("idle");
      return;
    }
    setStartState("running");
    setServerState("online");
  }

  async function stopServer(): Promise<void> {
    await window.emusync.server.stop();
    setStartState("idle");
    setServerState("offline");
  }

  async function saveDeviceName(): Promise<void> {
    const cfg = (await window.emusync.config.load()) ?? {};
    await window.emusync.config.save({ ...cfg, device_name: deviceName });
  }

  async function toggleWatchSaves(on: boolean): Promise<void> {
    setWatchSaves(on);
    const cfg = (await window.emusync.config.load()) ?? {};
    await window.emusync.config.save({ ...cfg, watch_saves: on });
    // sync-daemon reads watch_saves at startup, so it needs a restart to apply.
    await window.emusync.daemon.stop();
    await window.emusync.daemon.start();
  }

  async function clearRememberedFolders(): Promise<void> {
    const cfg = (await window.emusync.config.load()) ?? {};
    await window.emusync.config.save({ ...cfg, recent_import_folders: {}, import_rom_source: {}, import_local_folder: {}, import_network_folder: {}, import_ignored_roms: {} });
    setClearConfirm(false);
  }

  async function saveArtKey(): Promise<string | void> {
    const result = await window.emusync.steamgriddb.setKey(artKeyInput.trim());
    if (!result.ok) return result.error || "Failed to save key.";
  }

  async function applyPin(): Promise<void> {
    const pin = pinInput.trim() || null;
    if (pin && !/^\d{4}$/.test(pin)) {
      setPinError("PIN must be exactly 4 digits.");
      return;
    }
    setPinBusy(true);
    setPinError("");
    setPinConfirming(false);
    setStartState("starting");
    try {
      const result = await window.emusync.server.changePin(pin);
      if (!result.ok) {
        setPinError("Failed to restart server.");
        setStartState("idle");
        return;
      }
      setStartState("running");
      setServerState("online");
    } catch {
      setPinError("Failed to restart server.");
      setStartState("idle");
    } finally {
      setPinBusy(false);
    }
  }

  async function doConnect(): Promise<void> {
    if (!pairHost) {
      setPairError("Host is required.");
      return;
    }

    // Warn if this machine is currently acting as a server
    const connectingToExternal = pairHost !== "localhost" && pairHost !== "127.0.0.1";
    if (connectingToExternal && isServer && serverState === "online" && !pairServerWarning) {
      setPairServerWarning(true);
      return;
    }

    // Stop local server before connecting as client
    if (connectingToExternal && serverState === "online") {
      await window.emusync.server.stop();
      setStartState("idle");
      setServerState("offline");
    }

    setPairServerWarning(false);
    setPairBusy(true);
    setPairError("");
    setPairSuccess(false);
    try {
      const cfg      = (await window.emusync.config.load()) ?? {};
      const deviceId = (cfg.device_id as string) ?? crypto.randomUUID();
      const devName  = (cfg.device_name as string) ?? "unknown";
      const port     = parseInt(pairPort) || 8765;
      const pin      = pairPin.trim();

      // Verify we can reach the server with these credentials
      configure(pairHost, port, pin);
      configureDevice(deviceId, devName);
      if (!(await health())) {
        throw new Error("Could not reach the server. Check the address and make sure the server is running.");
      }

      await window.emusync.config.save({
        ...cfg,
        server_host: pairHost,
        server_port: port,
        server_pin: pin,
        device_id: deviceId,
        device_name: devName,
        is_server: false,
      });

      // Sync-daemon binds to the server host at its own startup, so it
      // needs a restart to pick up the new address (#433).
      await window.emusync.daemon.stop();
      await window.emusync.daemon.start();

      setPairSuccess(true);
      poll();
      onRepaired();
    } catch (e: unknown) {
      setPairError(e instanceof Error ? e.message : "Connection failed. Check the PIN and server address.");
    } finally {
      setPairBusy(false);
    }
  }

  const dot = serverState === "online" ? "var(--green)" : serverState === "offline" ? "var(--red)" : "var(--text-muted)";
  const label = serverState === "online" ? "Server online" : serverState === "offline" ? "Server offline" : "Checking…";

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        style={{
          display: "flex", alignItems: "center", gap: 7,
          background: "transparent", border: "2px solid var(--border)",
          borderRadius: "var(--radius)", padding: "5px 12px",
          cursor: "pointer", color: "var(--text)", fontSize: 12,
          transition: "background 0.15s",
        }}
        onMouseEnter={(e) => (e.currentTarget.style.background = "var(--surface2)")}
        onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
      >
        {serverState === "checking"
          ? <span className="spinner" />
          : <span style={{ width: 8, height: 8, borderRadius: "50%", background: dot, display: "inline-block" }} />}
        <span style={{ color: dot === "var(--text-muted)" ? "var(--text-muted)" : undefined }}>{label}</span>
      </button>

      {open && (
        <Modal size="md" style={{ width: 560 }} onClose={() => setOpen(false)}>
            <div className="modal-header">
              <h3>Settings</h3>
              <button className="btn btn-ghost" style={{ padding: "3px 8px" }} aria-label="Close" onClick={() => setOpen(false)}><CloseIcon /></button>
            </div>

            <div className="settings-heading first">Connection</div>
            {/* Status row — click to open activity popup */}
            <button
              onClick={() => setShowActivity(true)}
              style={{
                display: "flex", alignItems: "center", gap: 10,
                width: "100%", padding: "12px 14px", marginBottom: 14,
                background: "var(--bg)", borderRadius: "var(--radius)",
                border: "2px solid var(--border)", cursor: "pointer", textAlign: "left",
              }}
            >
              <span style={{ width: 10, height: 10, borderRadius: "50%", background: dot, display: "inline-block", flexShrink: 0 }} />
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 500, color: "var(--text)" }}>{label}</div>
                <div style={{ fontSize: 12, color: "var(--text-muted)" }}>Port {pairPort || 8765} · {pairHost || "localhost"}</div>
              </div>
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>click to see server activity →</span>
            </button>

            {/* Server machine controls */}
            {isServer && (
              <div style={{ marginBottom: 14 }}>
                <div style={{ fontSize: 12, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: 6 }}>This machine is the server</div>

                {/* Start/stop */}
                {startState === "idle" && serverState === "offline" && (
                  <div style={{ marginBottom: 12 }}>
                    {existingServers.length > 0 && !startWarningConfirmed && (
                      <div style={{ marginBottom: 10, padding: "10px 12px", background: "var(--bg)", border: "1px solid var(--red, #f87171)", borderRadius: "var(--radius)", fontSize: 12 }}>
                        <p style={{ color: "var(--red, #f87171)", marginBottom: 6, fontWeight: 500 }}><WarningIcon /> Another EmuSync server was found on your LAN:</p>
                        {existingServers.map((s) => (
                          <p key={s.host} style={{ color: "var(--text-muted)" }}>{s.name || "Unknown"} — {s.host}:{s.port}</p>
                        ))}
                        <p style={{ color: "var(--text-muted)", marginTop: 6 }}>Only one server should run per LAN. Start anyway?</p>
                        <div style={{ display: "flex", gap: 6, marginTop: 10 }}>
                          <button className="btn btn-danger" onClick={() => { setStartWarningConfirmed(true); handleStartServer(); }}>Start anyway</button>
                          <button className="btn btn-ghost" onClick={() => setExistingServers([])}>Cancel</button>
                        </div>
                      </div>
                    )}
                    {existingServers.length === 0 && (
                      <button className="btn btn-primary" style={{ width: "100%" }} onClick={handleStartServer}>
                        Start server
                      </button>
                    )}
                  </div>
                )}
                {startState === "starting" && (
                  <button className="btn btn-primary" style={{ width: "100%", marginBottom: 12 }} disabled>
                    <span className="spinner" /> Starting…
                  </button>
                )}
                {(startState === "running" || (startState === "idle" && serverState === "online")) && (
                  <button className="btn btn-danger" style={{ width: "100%", marginBottom: 12 }} onClick={stopServer}>
                    Stop server
                  </button>
                )}

                {/* PIN management */}
                <div style={{ borderTop: "2px solid var(--border)", paddingTop: 10 }}>
                  <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 6 }}>
                    PIN <span style={{ opacity: 0.6 }}>(optional — if no PIN, any device can connect)</span>
                  </div>
                  <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                    <PinInput
                      value={pinInput}
                      onChange={(v) => { setPinInput(v); setPinError(""); setPinConfirming(false); }}
                      style={{ width: 110, fontFamily: "monospace", letterSpacing: "0.1em", textAlign: "center" }}
                    />
                    {!pinConfirming ? (
                      <button className="btn btn-ghost" onClick={() => { setPinError(""); setPinConfirming(true); }} disabled={pinBusy}>
                        {pinInput ? "Set PIN" : "Clear PIN"}
                      </button>
                    ) : (
                      <div style={{ display: "flex", gap: 6 }}>
                        <button className="btn btn-danger" onClick={applyPin} disabled={pinBusy}>
                          {pinBusy ? <><span className="spinner" /> Restarting…</> : "Confirm"}
                        </button>
                        <button className="btn btn-ghost" onClick={() => setPinConfirming(false)} disabled={pinBusy}>Cancel</button>
                      </div>
                    )}
                  </div>
                  {pinConfirming && (
                    <p style={{ fontSize: 12, color: "var(--red, #f87171)", marginTop: 8 }}>
                      <WarningIcon /> This will restart the server. Other devices will need to update their PIN to reconnect.
                    </p>
                  )}
                  {pinError && <span role="alert" className="error-msg" style={{ marginTop: 4, display: "block" }}>{pinError}</span>}
                </div>
              </div>
            )}

            {/* Connect to server section — only show if this machine is NOT the server */}
            {!isServer && (
              <div style={{ borderTop: "2px solid var(--border)", paddingTop: 12 }}>
                <div style={{ fontSize: 12, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: 6 }}>
                  Connect to server
                </div>

                {pairServerWarning && (
                  <div style={{ marginBottom: 12, padding: "10px 12px", background: "var(--bg)", border: "1px solid var(--red, #f87171)", borderRadius: "var(--radius)", fontSize: 12 }}>
                    <p style={{ color: "var(--red, #f87171)", marginBottom: 6, fontWeight: 500 }}><WarningIcon /> This machine is currently running as a server</p>
                    <p style={{ color: "var(--text-muted)" }}>Connecting to an external host will stop this server. Continue?</p>
                    <div style={{ display: "flex", gap: 6, marginTop: 10 }}>
                      <button className="btn btn-danger" onClick={doConnect}>Stop server & connect</button>
                      <button className="btn btn-ghost" onClick={() => setPairServerWarning(false)}>Cancel</button>
                    </div>
                  </div>
                )}

                {!pairServerWarning && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    <div style={{ display: "flex", gap: 8 }}>
                      <div className="input-group" style={{ flex: 2 }}>
                        <label htmlFor="pair-host">Server host</label>
                        <input id="pair-host" type="text" value={pairHost} onChange={(e) => setPairHost(e.target.value)} placeholder="192.168.1.50" />
                      </div>
                      <div className="input-group" style={{ flex: 1 }}>
                        <label htmlFor="pair-port">Port</label>
                        <input id="pair-port" type="number" value={pairPort} onChange={(e) => setPairPort(e.target.value)} />
                      </div>
                    </div>
                    <div className="input-group">
                      <label htmlFor="pair-pin">PIN <span style={{ opacity: 0.6, fontWeight: 400 }}>(optional)</span></label>
                      <PinInput
                        id="pair-pin"
                        value={pairPin}
                        onChange={setPairPin}
                        className={pairError ? "error" : ""}
                      />
                      {pairError && <span role="alert" className="error-msg">{pairError}</span>}
                      {pairSuccess && <span style={{ fontSize: 12, color: "var(--green)" }}>Connected successfully.</span>}
                    </div>
                    <button className="btn btn-primary" onClick={doConnect} disabled={pairBusy || !pairHost.trim()}>
                      {pairBusy ? <><span className="spinner" /> Connecting…</> : "Connect"}
                    </button>
                  </div>
                )}
              </div>
            )}

            <div className="settings-heading">This device</div>
            <SaveField label="Device name" value={deviceName} onChange={setDeviceName} onSave={saveDeviceName} placeholder="My Gaming PC" />
            <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10, fontSize: 13, cursor: "pointer" }}>
              <input type="checkbox" checked={watchSaves} onChange={(e) => toggleWatchSaves(e.target.checked)} />
              Watch for save changes in the background
            </label>

            <div className="settings-heading">Game art</div>
            <SaveField
              label={<>SteamGridDB API key <span style={{ opacity: 0.6, fontWeight: 400, textTransform: "none" }}>(optional — shared with all devices)</span></>}
              value={artKeyInput}
              onChange={setArtKeyInput}
              onSave={saveArtKey}
              placeholder="Paste your SteamGridDB API key"
            />
            <button className="btn btn-ghost" onClick={() => window.emusync.steamgriddb.openKeyPage()} style={{ fontSize: 12, marginTop: 6 }}>
              Get a key from SteamGridDB →
            </button>

            <div className="settings-heading">Display</div>
            <div style={{ display: "flex", gap: 8 }}>
              <button
                className="btn btn-ghost"
                title="Cycle UI size (100 / 125 / 150 / 200%)"
                onClick={() => window.emusync.display.cycleScale().then((scale) => onDisplay({ scale }))}
              >
                UI size: {Math.round(display.scale * 100)}%
              </button>
              <button
                className="btn btn-ghost"
                title="Toggle fullscreen (F11 / Alt+Enter)"
                onClick={() => window.emusync.display.toggleFullscreen().then((fullscreen) => onDisplay({ fullscreen }))}
              >
                Fullscreen: {display.fullscreen ? "on" : "off"}
              </button>
            </div>
            <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10, fontSize: 13, cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={display.autoUpdateEnabled}
                onChange={(e) => {
                  const on = e.target.checked;
                  window.emusync.updater.setEnabled(on).then(() => onDisplay({ autoUpdateEnabled: on }));
                }}
              />
              Automatically check for and download updates
            </label>

            <details className="settings-collapse">
              <summary className="settings-heading">Details</summary>
              <div style={{ fontSize: 12, color: "var(--text-muted)", display: "grid", gridTemplateColumns: "auto 1fr", gap: "4px 12px", marginBottom: 10 }}>
                <span>Device ID</span>
                <span style={{ fontFamily: "monospace", wordBreak: "break-all" }}>{deviceId}</span>
                <span>Data folder</span>
                <span style={{ fontFamily: "monospace", wordBreak: "break-all" }}>{dataDir}</span>
                <span>Server port</span>
                <span style={{ fontFamily: "monospace" }}>{pairPort}</span>
                <span>Config file</span>
                <span style={{ fontFamily: "monospace" }}>emusync.toml (in the config folder)</span>
              </div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button
                  className="btn btn-ghost"
                  onClick={() => navigator.clipboard.writeText(deviceId).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000); })}
                >
                  {copied ? "Copied" : "Copy device ID"}
                </button>
                {!clearConfirm ? (
                  <button className="btn btn-ghost" onClick={() => setClearConfirm(true)}>Clear remembered import folders</button>
                ) : (
                  <>
                    <button className="btn btn-danger" onClick={clearRememberedFolders}>Confirm clear</button>
                    <button className="btn btn-ghost" onClick={() => setClearConfirm(false)}>Cancel</button>
                  </>
                )}
              </div>
            </details>

            <details className="settings-collapse">
              <summary className="settings-heading">Paired devices ({devices.length})</summary>
              <DevicesPanel />
            </details>
          </Modal>
      )}

      {/* Activity popup */}
      {showActivity && (
        <Modal size="md" onClose={() => setShowActivity(false)}>
            <div className="modal-header">
              <h3>Server activity</h3>
              <button className="btn btn-ghost" style={{ padding: "3px 8px" }} aria-label="Close" onClick={() => setShowActivity(false)}><CloseIcon /></button>
            </div>
            {eventsLoading ? (
              <div style={{ textAlign: "center", padding: 40 }}><span className="spinner" style={{ width: 22, height: 22 }} /></div>
            ) : events.length === 0 ? (
              <p style={{ color: "var(--text-muted)", fontSize: 13, textAlign: "center", padding: 40, margin: 0 }}>No activity yet.</p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", maxHeight: 400, overflowY: "auto" }}>
                {events.map((e, i) => {
                  const icons: Record<string, React.ReactNode> = {
                    server_started: <span style={{ color: "var(--green, #4caf50)" }}><DotIcon /></span>,
                    game_started: <PlayIcon />,
                    game_stopped: <StopIcon />,
                    save_synced: <UploadIcon />,
                  };
                  const descriptions: Record<string, (ev: ActivityEvent) => string> = {
                    server_started: () => "Server started",
                    game_started: (ev) => `${ev.game_slug} started${ev.device_name ? ` on ${ev.device_name}` : ""}`,
                    game_stopped: (ev) => `${ev.game_slug} stopped${ev.device_name ? ` on ${ev.device_name}` : ""}`,
                    save_synced: (ev) => `${ev.game_slug} synced${ev.device_name ? ` from ${ev.device_name}` : ""}`,
                  };
                  return (
                    <div key={i} style={{ display: "flex", alignItems: "baseline", gap: 10, padding: "8px 4px", borderBottom: i < events.length - 1 ? "2px solid var(--border)" : "none" }}>
                      <span style={{ fontSize: 13, minWidth: 18, textAlign: "center" }}>{icons[e.type] ?? "•"}</span>
                      <span style={{ flex: 1, fontSize: 13 }}>{(descriptions[e.type] ?? (() => e.type))(e)}</span>
                      <RelTime iso={e.occurred_at} fallback="" style={{ fontSize: 11, color: "var(--text-muted)", whiteSpace: "nowrap" }} />
                    </div>
                  );
                })}
              </div>
            )}
          </Modal>
      )}
    </>
  );
}
