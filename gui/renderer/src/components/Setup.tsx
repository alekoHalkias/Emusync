import React, { useEffect, useState } from "react";
import { configure, configureDevice, health, whoami } from "../api";
import PinInput from "./settings/PinInput";

type Step =
  | "choose"
  | "server-starting"
  | "server-ready"
  | "art-prompt"
  | "art-key-paste"
  | "join-scanning"
  | "join-select"
  | "join-pin"
  | "join-name";

type DiscoveredServer = { name: string; host: string; port: number };

// `window.emusync` is typed globally in src/emusync.d.ts (matches preload.ts).

type Props = { onDone: () => void };

export default function Setup({ onDone }: Props): React.ReactElement {
  const [step, setStep] = useState<Step>("choose");
  const [servers, setServers] = useState<DiscoveredServer[]>([]);
  const [selectedServer, setSelectedServer] = useState<DiscoveredServer | null>(null);
  const [inputPin, setInputPin] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [deviceName, setDeviceName] = useState("");
  const [artKey, setArtKey] = useState("");
  const [artKeyError, setArtKeyError] = useState("");
  const [artKeyBusy, setArtKeyBusy] = useState(false);
  const [manualHost, setManualHost] = useState("");
  const [manualPort, setManualPort] = useState("8765");
  // Stable across the verify probes and the final connect so the server
  // registers this device exactly once.
  const [deviceId, setDeviceId] = useState("");
  const [preflightError, setPreflightError] = useState("");

  useEffect(() => {
    window.emusync.server.preflight().then((r) => { if (!r.ok) setPreflightError(r.error ?? "Python install looks broken."); });
    window.emusync.config.load().then((cfg) => {
      if (cfg?.device_name) setDeviceName(cfg.device_name as string);
      setDeviceId((cfg?.device_id as string) ?? crypto.randomUUID());
    });
  }, []);

  async function startServer(): Promise<void> {
    setStep("server-starting");
    const existing  = (await window.emusync.config.load()) ?? {};
    const devName   = deviceName || (existing.device_name as string) || "Server";
    const deviceId  = (existing.device_id as string) ?? crypto.randomUUID();
    const port      = (existing.server_port as number) || 8765;
    const pin       = (existing.server_pin as string) || "";

    await window.emusync.config.save({
      ...existing,
      is_server: true,
      device_name: devName,
      device_id: deviceId,
    });

    const fail = async (msg: string): Promise<void> => {
      // Don't leave is_server=true behind, or every relaunch skips Setup and silently retries.
      await window.emusync.config.save({ ...existing, is_server: existing.is_server ?? false });
      await window.emusync.server.stop();
      setError(msg);
      setStep("choose");
    };

    const result = await window.emusync.server.start();
    if (!result.ok) {
      await fail(result.error || "Failed to start server. Make sure Python and emusync.py are available.");
      return;
    }

    // Wait for server to be ready before proceeding
    configure("localhost", port, pin);
    configureDevice(deviceId, devName);
    let up = false;
    for (let i = 0; i < 100 && !up; i++) {
      up = await health();
      if (!up) await new Promise<void>((r) => setTimeout(r, 100));
    }
    if (!up) {
      await fail(`The server did not respond on port ${port}. Is the port already in use?`);
      return;
    }

    setStep("server-ready");
  }

  async function scanServers(): Promise<void> {
    setStep("join-scanning");
    setSelectedServer(null);
    setError("");
    let found: DiscoveredServer[] = [];
    try {
      found = await window.emusync.server.discover();
    } catch {
      // fall through to manual entry
    }
    setServers(found);
    if (found.length === 1) setSelectedServer(found[0]);
    setStep("join-select");
  }

  function joinTarget(): DiscoveredServer | null {
    if (servers.length > 0) return selectedServer;
    const host = manualHost.trim();
    const port = parseInt(manualPort);
    if (!host || !(port >= 1 && port <= 65535)) return null;
    return { name: "", host, port };
  }

  // Probe the chosen server: reachable? open or PIN-protected? Skips the PIN
  // screen for open servers; a wrong PIN stays on the PIN screen.
  async function verifyServer(pin: string, fromPinStep: boolean): Promise<void> {
    const target = joinTarget();
    if (!target) {
      setError("Enter a valid host and port.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      setSelectedServer(target);
      configure(target.host, target.port, pin);
      configureDevice(deviceId, deviceName || "unknown");
      if (!(await health())) {
        throw new Error("Could not reach the server. Check the address and make sure it is running.");
      }
      try {
        await whoami();
      } catch (e: unknown) {
        // Blank-PIN probe failing on auth just means "ask for the PIN".
        if (!fromPinStep && pin === "") {
          setStep("join-pin");
          return;
        }
        throw e;
      }
      setInputPin(pin);
      setStep("join-name");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Connection failed.");
    } finally {
      setBusy(false);
    }
  }

  async function doConnect(): Promise<void> {
    if (!selectedServer) {
      setError("Enter the server details.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const cfg      = (await window.emusync.config.load()) ?? {};
      const devName  = deviceName || (cfg.device_name as string) || "unknown";
      const pin      = inputPin.trim();

      // Verify connection before saving
      configure(selectedServer.host, selectedServer.port, pin);
      configureDevice(deviceId, devName);
      if (!(await health())) {
        throw new Error("Could not reach the server. Check the address and make sure the server is running.");
      }

      await window.emusync.config.save({
        ...cfg,
        server_host: selectedServer.host,
        server_port: selectedServer.port,
        server_pin: pin,
        device_id: deviceId,
        device_name: devName,
        is_server: false,
      });
      onDone();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Connection failed. Check the PIN and server address.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="setup-wrap">
      <div className="card setup-card">
        {step === "choose" && (
          <>
            <h1>Welcome to EmuSync</h1>
            <p>Keep game saves in sync across your devices on your home network.</p>
            {preflightError && <p className="error-msg" style={{ margin: "12px 0", whiteSpace: "pre-wrap" }}>{preflightError}</p>}

            <div className="input-group" style={{ margin: "20px 0" }}>
              <label htmlFor="setup-device-name">What should we call this device?</label>
              <input id="setup-device-name"
                type="text"
                value={deviceName}
                onChange={(e) => setDeviceName(e.target.value)}
                placeholder="My Gaming PC"
                autoFocus
              />
            </div>

            {error && <p role="alert" className="error-msg" style={{ marginBottom: 16 }}>{error}</p>}
            <div className="setup-choices">
              <button type="button" className="setup-choice" onClick={startServer}>
                <span className="setup-choice-icon">🖥️</span>
                <div className="setup-choice-text">
                  <h3>Set up this as the server</h3>
                  <p>This is your gaming PC. Saves are stored here. Run this on your main machine first.</p>
                </div>
              </button>
              <button type="button" className="setup-choice" onClick={scanServers}>
                <span className="setup-choice-icon">🎮</span>
                <div className="setup-choice-text">
                  <h3>Join an existing server</h3>
                  <p>This is your Steam Deck or second device. Connect to the server running on your gaming PC.</p>
                </div>
              </button>
            </div>
          </>
        )}

        {step === "server-starting" && (
          <div style={{ textAlign: "center", padding: "40px 0" }}>
            <div className="spinner" style={{ width: 32, height: 32, margin: "0 auto 16px" }} />
            <p>Starting EmuSync server…</p>
          </div>
        )}

        {step === "server-ready" && (
          <>
            <h1>Server is running!</h1>
            <p style={{ marginBottom: 16 }}>
              Your EmuSync server is ready. Other devices on your network can now connect.
            </p>
            <p style={{ marginBottom: 24, fontSize: 13, color: "var(--text-muted, #888)" }}>
              To require a PIN, open the server settings from the top-right button after continuing.
              If no PIN is set, any device on your LAN can connect.
            </p>
            <button className="btn btn-primary" onClick={() => setStep("art-prompt")} style={{ width: "100%" }}>
              Continue
            </button>
          </>
        )}

        {step === "art-prompt" && (
          <>
            <h1>Game art</h1>
            <p style={{ marginBottom: 24 }}>
              Would you like to use SteamGridDB to fetch box art for your games?
              This is configured once here and shared with every device that
              connects to this server.
            </p>
            <div style={{ display: "flex", gap: 10 }}>
              <button className="btn btn-ghost" style={{ flex: 1 }} onClick={onDone}>
                Skip for now
              </button>
              <button
                className="btn btn-primary"
                style={{ flex: 1 }}
                onClick={async () => {
                  await window.emusync.steamgriddb.openKeyPage();
                  setStep("art-key-paste");
                }}
              >
                Yes
              </button>
            </div>
          </>
        )}

        {step === "art-key-paste" && (
          <>
            <h1>Paste your SteamGridDB API key</h1>
            <p style={{ marginBottom: 16 }}>
              Log in with Steam on the page that just opened, then copy your
              API key from the "API" tab and paste it below.
            </p>
            <div className="input-group" style={{ marginBottom: 16 }}>
              <label htmlFor="setup-api-key">API key</label>
              <input id="setup-api-key"
                type="text"
                value={artKey}
                onChange={(e) => { setArtKey(e.target.value); setArtKeyError(""); }}
                placeholder="Paste your key here"
                className={artKeyError ? "error" : ""}
                autoFocus
              />
              {artKeyError && <span role="alert" className="error-msg">{artKeyError}</span>}
            </div>
            <div style={{ display: "flex", gap: 10 }}>
              <button className="btn btn-ghost" onClick={onDone} disabled={artKeyBusy}>
                Skip
              </button>
              <button
                className="btn btn-primary"
                style={{ flex: 1 }}
                disabled={artKeyBusy || !artKey.trim()}
                onClick={async () => {
                  setArtKeyBusy(true);
                  setArtKeyError("");
                  const result = await window.emusync.steamgriddb.setKey(artKey.trim());
                  setArtKeyBusy(false);
                  if (result.ok) {
                    onDone();
                  } else {
                    setArtKeyError(result.error || "Failed to save key.");
                  }
                }}
              >
                {artKeyBusy ? <><span className="spinner" /> Saving…</> : "Save"}
              </button>
            </div>
          </>
        )}

        {step === "join-scanning" && (
          <div style={{ textAlign: "center", padding: "40px 0" }}>
            <div className="spinner" style={{ width: 32, height: 32, margin: "0 auto 16px" }} />
            <p>Scanning for EmuSync servers…</p>
          </div>
        )}

        {step === "join-select" && (
          <>
            <h1>Connect to server</h1>
            {servers.length === 0 ? (
              <>
                <p>No servers found automatically. Enter the server details manually.</p>
                <div className="input-group" style={{ marginTop: 16 }}>
                  <label htmlFor="setup-host">Server host</label>
                  <input id="setup-host"
                    type="text"
                    placeholder="192.168.1.50"
                    value={manualHost}
                    onChange={(e) => setManualHost(e.target.value)}
                  />
                </div>
                <div className="input-group" style={{ marginTop: 12 }}>
                  <label htmlFor="setup-port">Port</label>
                  <input id="setup-port"
                    type="number"
                    value={manualPort}
                    onChange={(e) => setManualPort(e.target.value)}
                  />
                </div>
              </>
            ) : (
              <>
                <p>Found {servers.length} server{servers.length > 1 ? "s" : ""} on your network:</p>
                <div className="server-list">
                  {servers.map((s) => (
                    <div
                      key={s.host}
                      className="server-item"
                      style={{ borderColor: selectedServer?.host === s.host ? "var(--accent)" : undefined }}
                      onClick={() => setSelectedServer(s)}
                    >
                      <div>
                        <div style={{ fontWeight: 500 }}>{s.name || "EmuSync Server"}</div>
                        <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{s.host}:{s.port}</div>
                      </div>
                      {selectedServer?.host === s.host && <span>✓</span>}
                    </div>
                  ))}
                </div>
              </>
            )}
            {error && <p role="alert" className="error-msg" style={{ marginTop: 12 }}>{error}</p>}
            <div style={{ display: "flex", gap: 10, marginTop: 20 }}>
              <button className="btn btn-ghost" onClick={scanServers} disabled={busy}>
                Rescan
              </button>
              <button
                className="btn btn-primary"
                style={{ flex: 1 }}
                disabled={busy || !joinTarget()}
                onClick={() => verifyServer("", false)}
              >
                {busy ? <><span className="spinner" /> Checking…</> : "Next"}
              </button>
            </div>
          </>
        )}

        {step === "join-pin" && (
          <>
            <h1>Enter PIN</h1>
            <p>This server requires a PIN. It is shown in the server's settings on the gaming PC.</p>
            <div className="input-group" style={{ margin: "16px 0" }}>
              <label htmlFor="setup-pin">PIN</label>
              <PinInput
                id="setup-pin"
                value={inputPin}
                onChange={(v) => { setInputPin(v); setError(""); }}
                onKeyDown={(e) => { if (e.key === "Enter" && inputPin) verifyServer(inputPin, true); }}
                className={error ? "error" : ""}
                autoFocus
              />
              {error && <span role="alert" className="error-msg">{error}</span>}
            </div>
            <div style={{ display: "flex", gap: 10 }}>
              <button className="btn btn-ghost" onClick={() => { setError(""); setStep("join-select"); }} disabled={busy}>
                Back
              </button>
              <button className="btn btn-primary" onClick={() => verifyServer(inputPin, true)} disabled={busy || !inputPin} style={{ flex: 1 }}>
                {busy ? <><span className="spinner" /> Checking…</> : "Next"}
              </button>
            </div>
          </>
        )}

        {step === "join-name" && (
          <>
            <h1>Device Name</h1>
            <p>What would you like to name this device on the server?</p>
            <div className="input-group" style={{ margin: "16px 0" }}>
              <label htmlFor="setup-device-name2">Device name <span style={{ color: "var(--error)" }}>*</span></label>
              <input id="setup-device-name2"
                type="text"
                placeholder="My Device"
                value={deviceName}
                onChange={(e) => setDeviceName(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && deviceName.trim()) doConnect(); }}
                className={error ? "error" : ""}
                autoFocus
              />
              {!deviceName.trim() && <span role="alert" className="error-msg">Device name is required</span>}
              {error && <span role="alert" className="error-msg">{error}</span>}
            </div>
            <div style={{ display: "flex", gap: 10 }}>
              <button className="btn btn-ghost" onClick={() => { setError(""); setStep(inputPin ? "join-pin" : "join-select"); }} disabled={busy}>
                Back
              </button>
              <button className="btn btn-primary" onClick={doConnect} disabled={busy || !deviceName.trim()} style={{ flex: 1 }}>
                {busy ? <><span className="spinner" /> Connecting…</> : "Connect"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
