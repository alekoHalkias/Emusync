import React, { useEffect, useState } from "react";
import { pair } from "../api";
import { configure } from "../api";

type Step =
  | "choose"
  | "server-starting"
  | "server-ready"
  | "join-scanning"
  | "join-select"
  | "join-token";

type DiscoveredServer = { name: string; host: string; port: number };

declare global {
  interface Window {
    emusync: {
      config: {
        load: () => Promise<Record<string, unknown> | null>;
        save: (data: Record<string, unknown>) => Promise<boolean>;
        exists: () => Promise<boolean>;
      };
      server: {
        start: () => Promise<{ ok: boolean; token: string | null }>;
        stop: () => Promise<boolean>;
        token: () => Promise<string | null>;
        changePin: (pin: string | null) => Promise<{ ok: boolean; token: string | null }>;
        discover: () => Promise<Array<{ name: string; host: string; port: number }>>;
      };
      dialog: {
        openFile: (opts?: { title?: string; filters?: { name: string; extensions: string[] }[] }) => Promise<string | null>;
      };
    };
  }
}

type Props = { onDone: () => void };

export default function Setup({ onDone }: Props): React.ReactElement {
  const [step, setStep] = useState<Step>("choose");
  const [servers, setServers] = useState<DiscoveredServer[]>([]);
  const [selectedServer, setSelectedServer] = useState<DiscoveredServer | null>(null);
  const [inputToken, setInputToken] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [deviceName, setDeviceName] = useState("");

  useEffect(() => {
    window.emusync.config.load().then((cfg) => {
      if (cfg?.device_name) setDeviceName(cfg.device_name as string);
    });
  }, []);

  async function startServer(): Promise<void> {
    setStep("server-starting");
    const existing   = (await window.emusync.config.load()) ?? {};
    const devName    = deviceName || (existing.device_name as string) || "Server";
    const deviceId   = (existing.device_id as string) ?? crypto.randomUUID();
    await window.emusync.config.save({ ...existing, is_server: true, device_name: devName, device_id: deviceId });
    const result = await window.emusync.server.start();
    if (!result.ok) {
      setError("Failed to start server. Make sure Python and emusync.py are available.");
      setStep("choose");
      return;
    }
    // Self-pair so this machine can use its own API (add/import games, etc.)
    try {
      configure("localhost", (existing.server_port as number) || 8765, "");
      const token = await pair(result.token || "", deviceId, devName);
      await window.emusync.config.save({
        ...existing, is_server: true, device_name: devName, device_id: deviceId, token,
      });
      configure("localhost", (existing.server_port as number) || 8765, token);
    } catch { /* non-fatal; user can still continue */ }
    setStep("server-ready");
  }

  async function scanServers(): Promise<void> {
    setStep("join-scanning");
    setServers([]);
    setStep("join-select");
  }

  async function doPair(): Promise<void> {
    if (!selectedServer) {
      setError("Enter the server details.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      configure(selectedServer.host, selectedServer.port, "");
      const cfg = (await window.emusync.config.load()) ?? {};
      const deviceId = (cfg.device_id as string) ?? crypto.randomUUID();
      const devName = deviceName || (cfg.device_name as string) || "unknown";
      const token = await pair(inputToken.trim(), deviceId, devName);
      await window.emusync.config.save({
        ...cfg,
        server_host: selectedServer.host,
        server_port: selectedServer.port,
        device_id: deviceId,
        device_name: devName,
        token,
        is_server: false,
      });
      onDone();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Pairing failed. Check the PIN and server address.");
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

            <div className="input-group" style={{ margin: "20px 0" }}>
              <label>What should we call this device?</label>
              <input
                type="text"
                value={deviceName}
                onChange={(e) => setDeviceName(e.target.value)}
                placeholder="My Gaming PC"
                autoFocus
              />
            </div>

            {error && <p className="error-msg" style={{ marginBottom: 16 }}>{error}</p>}
            <div className="setup-choices">
              <div className="setup-choice" onClick={startServer}>
                <span className="setup-choice-icon">🖥️</span>
                <div className="setup-choice-text">
                  <h3>Set up this as the server</h3>
                  <p>This is your gaming PC. Saves are stored here. Run this on your main machine first.</p>
                </div>
              </div>
              <div className="setup-choice" onClick={scanServers}>
                <span className="setup-choice-icon">🎮</span>
                <div className="setup-choice-text">
                  <h3>Join an existing server</h3>
                  <p>This is your Steam Deck or second device. Connect to the server running on your gaming PC.</p>
                </div>
              </div>
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
            <button className="btn btn-primary" onClick={onDone} style={{ width: "100%" }}>
              Continue to game list
            </button>
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
                  <label>Server host</label>
                  <input
                    type="text"
                    placeholder="192.168.1.50"
                    onChange={(e) =>
                      setSelectedServer((s) => ({ ...(s ?? { name: "", port: 8765 }), host: e.target.value }))
                    }
                  />
                </div>
                <div className="input-group" style={{ marginTop: 12 }}>
                  <label>Port</label>
                  <input
                    type="number"
                    defaultValue={8765}
                    onChange={(e) =>
                      setSelectedServer((s) => ({
                        ...(s ?? { name: "", host: "" }),
                        port: parseInt(e.target.value) || 8765,
                      }))
                    }
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
            <button
              className="btn btn-primary"
              style={{ marginTop: 20, width: "100%" }}
              disabled={!selectedServer?.host}
              onClick={() => setStep("join-token")}
            >
              Next
            </button>
          </>
        )}

        {step === "join-token" && (
          <>
            <h1>Enter PIN</h1>
            <p>If the server has a PIN set, enter it below. Otherwise leave it blank.</p>
            <div className="input-group" style={{ margin: "16px 0" }}>
              <label>PIN <span style={{ opacity: 0.6, fontWeight: 400 }}>(optional)</span></label>
              <input
                type="text"
                inputMode="numeric"
                maxLength={4}
                placeholder="1234"
                value={inputToken}
                onChange={(e) => setInputToken(e.target.value.replace(/\D/g, ""))}
                className={error ? "error" : ""}
                autoFocus
              />
              {error && <span className="error-msg">{error}</span>}
            </div>
            <div style={{ display: "flex", gap: 10 }}>
              <button className="btn btn-ghost" onClick={() => setStep("join-select")} disabled={busy}>
                Back
              </button>
              <button className="btn btn-primary" onClick={doPair} disabled={busy} style={{ flex: 1 }}>
                {busy ? <><span className="spinner" /> Pairing…</> : "Connect"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
