// One tabbed modal consolidating all per-game actions (issue #260): Settings
// (the GameConfig editor, with Delete), Devices, Save history, and Run.
import React, { useEffect, useState } from "react";
import ArtworkTab from "./ArtworkTab";
import GameConfig from "./GameConfig";
import GameDeviceModal from "./game-list/GameDeviceModal";
import SaveHistory from "./SaveHistory";

export type GameModalTarget = {
  slug: string;
  name: string;
  gameConsole: string;
  consoleKey: string;
  gameIsLocal: boolean;
  savePath?: string;
  statePath?: string;
  canPlay: boolean;
};

type Tab = "settings" | "artwork" | "devices" | "history" | "run";

export default function GameModal({ target, onClose, onChanged, onLaunch }: {
  target: GameModalTarget;
  onClose: () => void;
  onChanged: () => void;                       // reload the game list after a change
  onLaunch: (slug: string, name: string) => void;
}): React.ReactElement {
  const [tab, setTab] = useState<Tab>("settings");
  const { slug, name, gameConsole, consoleKey, gameIsLocal, savePath, statePath, canPlay } = target;

  const tabs: { key: Tab; label: string; disabled?: boolean }[] = [
    { key: "settings", label: "Settings" },
    { key: "artwork", label: "Artwork" },
    { key: "devices", label: "Devices" },
    { key: "history", label: "Save history" },
    { key: "run", label: "Run", disabled: !canPlay },
  ];

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ width: 760, maxWidth: "92vw" }} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
          <h3 style={{ margin: 0 }}>{name}</h3>
          <button className="btn btn-ghost" onClick={onClose}>✕</button>
        </div>

        <div style={{ display: "flex", gap: 4, borderBottom: "1px solid var(--border)", marginBottom: 16 }}>
          {tabs.map((t) => (
            <button
              key={t.key}
              className="btn btn-ghost"
              disabled={t.disabled}
              onClick={() => setTab(t.key)}
              style={{
                borderRadius: 0,
                borderBottom: tab === t.key ? "2px solid var(--accent, #7c8cf8)" : "2px solid transparent",
                opacity: t.disabled ? 0.4 : 1,
                fontWeight: tab === t.key ? 600 : 400,
              }}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div style={{ maxHeight: "70vh", overflowY: "auto" }}>
          {tab === "settings" && (
            <GameConfig
              embedded
              slug={slug}
              name={name}
              onBack={onClose}
              onSaved={() => { onChanged(); onClose(); }}
              onRemoved={() => { onChanged(); onClose(); }}
            />
          )}
          {tab === "artwork" && (
            <ArtworkTab slug={slug} name={name} consoleKey={consoleKey} />
          )}
          {tab === "devices" && (
            <GameDeviceModal embedded slug={slug} name={name} gameConsole={gameConsole} gameIsLocal={gameIsLocal} onClose={onClose} />
          )}
          {tab === "history" && (
            <SaveHistory embedded slug={slug} name={name} savePath={savePath} statePath={statePath} onClose={onClose} onRestored={onChanged} />
          )}
          {tab === "run" && (
            <RunTab slug={slug} name={name} canPlay={canPlay} onLaunch={onLaunch} onClose={onClose} />
          )}
        </div>
      </div>
    </div>
  );
}

function RunTab({ slug, name, canPlay, onLaunch, onClose }: {
  slug: string;
  name: string;
  canPlay: boolean;
  onLaunch: (slug: string, name: string) => void;
  onClose: () => void;
}): React.ReactElement {
  const [launcherPath, setLauncherPath] = useState("emusync");
  const [copied, setCopied] = useState(false);
  useEffect(() => { window.emusync.launcher.path().then(setLauncherPath); }, []);

  // The %command% form makes `emusync run` wrap the real emulator so the lock is
  // acquired and the save synced (see the old PlayModal for the full rationale).
  const steamCommand = `"${launcherPath}" run ${slug} -- %command%`;

  function launch(): void {
    onLaunch(slug, name);
    onClose();
  }

  return (
    <div>
      <button
        className="btn btn-primary"
        style={{ width: "100%", marginBottom: 20 }}
        disabled={!canPlay}
        onClick={launch}
      >
        ▶ Launch now
      </button>

      <p style={{ marginBottom: 6, fontWeight: 500 }}>Add to Steam</p>
      <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 8 }}>
        Paste this into Steam → game properties → launch options. Keep the
        <code> %command%</code> — Steam replaces it with the emulator command so EmuSync can wrap it.
      </p>
      <div style={{ display: "flex", gap: 8 }}>
        <input
          readOnly
          value={steamCommand}
          onFocus={(e) => e.currentTarget.select()}
          style={{ flex: 1, fontFamily: "monospace", fontSize: 12 }}
        />
        <button
          className="btn btn-ghost"
          onClick={() => { navigator.clipboard.writeText(steamCommand); setCopied(true); setTimeout(() => setCopied(false), 1500); }}
        >
          {copied ? "✓ Copied" : "Copy"}
        </button>
      </div>
    </div>
  );
}
