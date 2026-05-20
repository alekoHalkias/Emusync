import React, { useCallback, useEffect, useState } from "react";
import { configure, health, pair, listEvents, type ActivityEvent } from "../api";

type ServerState = "checking" | "online" | "offline";
type StartState = "idle" | "starting" | "running";

export default function ServerStatusButton({ isServer, onRepaired }: { isServer: boolean; onRepaired: () => void }): React.ReactElement {
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
  const [deviceNameSaved, setDeviceNameSaved] = useState(false);

  // Activity log
  const [showActivity, setShowActivity] = useState(false);
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [eventsLoading, setEventsLoading] = useState(false);

  // LAN discovery warning
  const [existingServers, setExistingServers] = useState<Array<{ name: string; host: string; port: number }>>([]);
  const [startWarningConfirmed, setStartWarningConfirmed] = useState(false);

  // Pairing form
  const [pairHost, setPairHost] = useState("");
  const [pairPort, setPairPort] = useState("8765");
  const [pairToken, setPairToken] = useState("");
  const [pairBusy, setPairBusy] = useState(false);
  const [pairError, setPairError] = useState("");
  const [pairSuccess, setPairSuccess] = useState(false);
  const [pairServerWarning, setPairServerWarning] = useState(false);

  const poll = useCallback(async () => {
    const ok = await health();
    setServerState(ok ? "online" : "offline");
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
      setDeviceName((cfg.device_name as string) || "");
      setPinInput((cfg.server_pin as string) || "");
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
    setDeviceNameSaved(true);
    setTimeout(() => setDeviceNameSaved(false), 2000);
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

  async function doPair(): Promise<void> {
    if (!pairHost) {
      setPairError("Host is required.");
      return;
    }

    // Warn if this machine is currently acting as a server
    const pairingToExternal = pairHost !== "localhost" && pairHost !== "127.0.0.1";
    if (pairingToExternal && isServer && serverState === "online" && !pairServerWarning) {
      setPairServerWarning(true);
      return;
    }

    // Stop local server before pairing as client
    if (pairingToExternal && serverState === "online") {
      await window.emusync.server.stop();
      setStartState("idle");
      setServerState("offline");
    }

    setPairServerWarning(false);
    setPairBusy(true);
    setPairError("");
    setPairSuccess(false);
    try {
      const cfg = (await window.emusync.config.load()) ?? {};
      const deviceId = (cfg.device_id as string) ?? crypto.randomUUID();
      const devName = (cfg.device_name as string) ?? "unknown";
      const port = parseInt(pairPort) || 8765;

      configure(pairHost, port, "");
      const newToken = await pair(pairToken.trim(), deviceId, devName);

      await window.emusync.config.save({
        ...cfg,
        server_host: pairHost,
        server_port: port,
        device_id: deviceId,
        device_name: devName,
        token: newToken,
        is_server: false,
      });

      configure(pairHost, port, newToken);
      setPairSuccess(true);
      setPairToken("");
      poll();
      onRepaired();
    } catch (e: unknown) {
      setPairError(e instanceof Error ? e.message : "Pairing failed. Check the code and server address.");
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
          background: "transparent", border: "1px solid var(--border)",
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
        <div className="modal-overlay" onClick={() => setOpen(false)}>
          <div className="modal" style={{ width: 460 }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
              <h3>Server connection</h3>
              <button className="btn btn-ghost" style={{ padding: "3px 8px" }} onClick={() => setOpen(false)}>✕</button>
            </div>

            {/* Status row — click to open activity popup */}
            <button
              onClick={() => setShowActivity(true)}
              style={{
                display: "flex", alignItems: "center", gap: 10,
                width: "100%", padding: "12px 14px", marginBottom: 20,
                background: "var(--bg)", borderRadius: "var(--radius)",
                border: "1px solid var(--border)", cursor: "pointer", textAlign: "left",
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
              <div style={{ marginBottom: 20 }}>
                <div style={{ fontSize: 12, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: 12 }}>This machine is the server</div>

                {/* Device name */}
                <div style={{ display: "flex", gap: 8, alignItems: "flex-end", marginBottom: 14 }}>
                  <div className="input-group" style={{ flex: 1, marginBottom: 0 }}>
                    <label>Server name</label>
                    <input
                      type="text"
                      value={deviceName}
                      onChange={(e) => { setDeviceName(e.target.value); setDeviceNameSaved(false); }}
                      placeholder="My Gaming PC"
                    />
                  </div>
                  <button className="btn btn-ghost" onClick={saveDeviceName} style={{ flexShrink: 0 }}>
                    {deviceNameSaved ? "Saved" : "Save"}
                  </button>
                </div>

                {/* Start/stop */}
                {startState === "idle" && serverState === "offline" && (
                  <div style={{ marginBottom: 12 }}>
                    {existingServers.length > 0 && !startWarningConfirmed && (
                      <div style={{ marginBottom: 10, padding: "10px 12px", background: "var(--bg)", border: "1px solid var(--red, #f87171)", borderRadius: "var(--radius)", fontSize: 12 }}>
                        <p style={{ color: "var(--red, #f87171)", marginBottom: 6, fontWeight: 500 }}>⚠ Another EmuSync server was found on your LAN:</p>
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
                <div style={{ borderTop: "1px solid var(--border)", paddingTop: 12 }}>
                  <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>
                    PIN <span style={{ opacity: 0.6 }}>(optional — if no PIN, any device can connect)</span>
                  </div>
                  <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                    <input
                      type="text"
                      inputMode="numeric"
                      maxLength={4}
                      value={pinInput}
                      onChange={(e) => { setPinInput(e.target.value.replace(/\D/g, "")); setPinError(""); setPinConfirming(false); }}
                      placeholder="1234"
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
                      ⚠ This will restart the server and disconnect all paired devices. They must re-pair.
                    </p>
                  )}
                  {pinError && <span className="error-msg" style={{ marginTop: 4, display: "block" }}>{pinError}</span>}
                </div>
              </div>
            )}

            {/* Pair / connect section */}
            <div style={{ borderTop: "1px solid var(--border)", paddingTop: 16 }}>
              <div style={{ fontSize: 12, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: 12 }}>
                {isServer ? "Re-pair this device" : "Connect to server"}
              </div>

              {pairServerWarning && (
                <div style={{ marginBottom: 12, padding: "10px 12px", background: "var(--bg)", border: "1px solid var(--red, #f87171)", borderRadius: "var(--radius)", fontSize: 12 }}>
                  <p style={{ color: "var(--red, #f87171)", marginBottom: 6, fontWeight: 500 }}>⚠ This machine is currently running as a server</p>
                  <p style={{ color: "var(--text-muted)" }}>Pairing to an external host will stop this server and disconnect all clients. Continue?</p>
                  <div style={{ display: "flex", gap: 6, marginTop: 10 }}>
                    <button className="btn btn-danger" onClick={doPair}>Stop server & pair</button>
                    <button className="btn btn-ghost" onClick={() => setPairServerWarning(false)}>Cancel</button>
                  </div>
                </div>
              )}

              {!pairServerWarning && (
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <div style={{ display: "flex", gap: 8 }}>
                    <div className="input-group" style={{ flex: 2 }}>
                      <label>Server host</label>
                      <input type="text" value={pairHost} onChange={(e) => setPairHost(e.target.value)} placeholder="192.168.1.50" />
                    </div>
                    <div className="input-group" style={{ flex: 1 }}>
                      <label>Port</label>
                      <input type="number" value={pairPort} onChange={(e) => setPairPort(e.target.value)} />
                    </div>
                  </div>
                  <div className="input-group">
                    <label>PIN <span style={{ opacity: 0.6, fontWeight: 400 }}>(optional)</span></label>
                    <input
                      type="text"
                      inputMode="numeric"
                      maxLength={4}
                      value={pairToken}
                      onChange={(e) => setPairToken(e.target.value.replace(/\D/g, ""))}
                      placeholder="1234"
                      className={pairError ? "error" : ""}
                    />
                    {pairError && <span className="error-msg">{pairError}</span>}
                    {pairSuccess && <span style={{ fontSize: 12, color: "var(--green)" }}>Paired successfully.</span>}
                  </div>
                  <button className="btn btn-primary" onClick={doPair} disabled={pairBusy || !pairHost.trim()}>
                    {pairBusy ? <><span className="spinner" /> Pairing…</> : "Pair device"}
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Activity popup */}
      {showActivity && (
        <div className="modal-overlay" onClick={() => setShowActivity(false)}>
          <div className="modal" style={{ width: 480 }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
              <h3>Server activity</h3>
              <button className="btn btn-ghost" style={{ padding: "3px 8px" }} onClick={() => setShowActivity(false)}>✕</button>
            </div>
            {eventsLoading ? (
              <div style={{ textAlign: "center", padding: 40 }}><span className="spinner" style={{ width: 22, height: 22 }} /></div>
            ) : events.length === 0 ? (
              <p style={{ color: "var(--text-muted)", fontSize: 13, textAlign: "center", padding: 40, margin: 0 }}>No activity yet.</p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", maxHeight: 400, overflowY: "auto" }}>
                {events.map((e, i) => {
                  const icons: Record<string, string> = {
                    server_started: "🟢",
                    game_started: "▶",
                    game_stopped: "■",
                    save_synced: "↑",
                  };
                  const descriptions: Record<string, (ev: ActivityEvent) => string> = {
                    server_started: () => "Server started",
                    game_started: (ev) => `${ev.game_slug} started${ev.device_name ? ` on ${ev.device_name}` : ""}`,
                    game_stopped: (ev) => `${ev.game_slug} stopped${ev.device_name ? ` on ${ev.device_name}` : ""}`,
                    save_synced: (ev) => `${ev.game_slug} synced${ev.device_name ? ` from ${ev.device_name}` : ""}`,
                  };
                  const time = e.occurred_at ? e.occurred_at.slice(0, 19).replace("T", " ") : "";
                  return (
                    <div key={i} style={{ display: "flex", alignItems: "baseline", gap: 10, padding: "8px 4px", borderBottom: i < events.length - 1 ? "1px solid var(--border)" : "none" }}>
                      <span style={{ fontSize: 13, minWidth: 18, textAlign: "center" }}>{icons[e.type] ?? "•"}</span>
                      <span style={{ flex: 1, fontSize: 13 }}>{(descriptions[e.type] ?? (() => e.type))(e)}</span>
                      <span style={{ fontSize: 11, color: "var(--text-muted)", whiteSpace: "nowrap" }}>{time}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
