import React, { useCallback, useEffect, useRef, useState } from "react";
import { addGame, getGame, getGameDevice, getDeviceConsoles, getSaveMeta, getStateMeta, setGameDevice, updateGame, whoami, type GameDeviceConfig, type SaveMeta } from "../api";
import { RelTime } from "../time";

type Props = {
  slug: string | null;
  name?: string;
  onBack: () => void;
  onSaved: () => void;
  onPlay?: (slug: string) => void;
};

type SyncOp = { status: "idle" | "busy" | "ok" | "error"; action: "push" | "pull" | null; msg: string };
const IDLE_OP: SyncOp = { status: "idle", action: null, msg: "" };



export default function GameConfig({ slug, name: initialName, onBack, onSaved, onPlay }: Props): React.ReactElement {
  const isNew = slug === null;
  const [name, setName] = useState(initialName ?? "");
  const [romPath, setRomPath] = useState("");
  const [savePath, setSavePath] = useState("");
  const [statePath, setStatePath] = useState("");
  const [launchCommand, setLaunchCommand] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState("");

  // Sync panel data
  const [localSaveTime, setLocalSaveTime] = useState<string | null>(null);
  const [serverSaveMeta, setServerSaveMeta] = useState<SaveMeta>(null);
  const [latestStateFile, setLatestStateFile] = useState<{ path: string; time: string } | null>(null);
  const [serverStateMeta, setServerStateMeta] = useState<SaveMeta>(null);
  const [saveOp, setSaveOp] = useState<SyncOp>(IDLE_OP);
  const [stateOp, setStateOp] = useState<SyncOp>(IDLE_OP);

  // Network-ROM source (issue #255): source + the on-demand local copy.
  const [romSource, setRomSource] = useState("local");
  const [localRomPath, setLocalRomPath] = useState("");
  const [localDestFolder, setLocalDestFolder] = useState("");  // console's configured local-copy folder
  const [romBusy, setRomBusy] = useState(false);
  const [romMsg, setRomMsg] = useState("");
  // Fields we preserve verbatim across a save (not editable in this form).
  const netExtraRef = useRef<{ rom_rel_path?: string; rom_sha256?: string; rom_folder_path?: string }>({});

  useEffect(() => {
    if (!slug) return;
    getGameDevice(slug)
      .then((cfg) => {
        setRomPath(cfg.rom_path);
        setSavePath(cfg.save_path);
        setStatePath(cfg.state_path ?? "");
        setLaunchCommand(cfg.launch_command);
        setRomSource(cfg.rom_source ?? "local");
        setLocalRomPath(cfg.local_rom_path ?? "");
        netExtraRef.current = {
          rom_rel_path: cfg.rom_rel_path ?? "",
          rom_sha256: cfg.rom_sha256 ?? "",
          rom_folder_path: cfg.rom_folder_path ?? "",
        };
      })
      .catch(() => setLoadError("Could not load device config — the server may be unreachable."));
  }, [slug]);

  // Resolve the console's configured local-copy destination for a network ROM,
  // so we can show it and localize without re-prompting (issue #255).
  useEffect(() => {
    if (!slug || romSource !== "network") { setLocalDestFolder(""); return; }
    (async () => {
      try {
        const game = await getGame(slug);
        const { device_id } = await whoami();
        const consoles = await getDeviceConsoles(device_id);
        const matches = consoles.filter(c => c.console_name === game.console);
        setLocalDestFolder(matches.find(c => c.device_local_folder)?.device_local_folder
          || matches[0]?.device_local_folder || "");
      } catch { setLocalDestFolder(""); }
    })();
  }, [slug, romSource]);

  const loadSyncInfo = useCallback(async () => {
    if (!slug) return;
    const [sm, ss] = await Promise.allSettled([getSaveMeta(slug), getStateMeta(slug)]);
    if (sm.status === "fulfilled") setServerSaveMeta(sm.value);
    if (ss.status === "fulfilled") setServerStateMeta(ss.value);
  }, [slug]);

  useEffect(() => {
    if (!savePath) return;
    window.emusync.files.getSaveTime(savePath).then(setLocalSaveTime).catch(() => {});
  }, [savePath]);

  useEffect(() => {
    if (!statePath) return;
    // statePath is now the state FOLDER itself
    window.emusync.files.getLatestInFolder(statePath).then(setLatestStateFile).catch(() => {});
  }, [statePath]);

  useEffect(() => { loadSyncInfo(); }, [loadSyncInfo]);

  async function pickFile(setter: (p: string) => void, title: string): Promise<void> {
    const path = await window.emusync.dialog.openFile({ title });
    if (path) setter(path);
  }

  // Copy this network ROM onto local disk for offline play (or remove the copy).
  async function handleLocalize(): Promise<void> {
    if (!slug) return;
    setRomBusy(true); setRomMsg("");
    // Use the console's configured destination if we have one; otherwise ask once.
    let folder = localDestFolder;
    if (!folder) {
      const picked = await window.emusync.dialog.openFolder();
      if (!picked) { setRomBusy(false); return; }
      folder = picked;
      setLocalDestFolder(picked);   // remember it locally; the copy teaches the console
    }
    const r = await window.emusync.rom.localize(slug, folder);
    if (r.ok) { setLocalRomPath(r.localPath ?? ""); setRomMsg("✓ Localized for offline play."); }
    else setRomMsg(r.error ?? "Localize failed.");
    setRomBusy(false);
  }

  async function handlePickDestFolder(): Promise<void> {
    const picked = await window.emusync.dialog.openFolder();
    if (picked) { setLocalDestFolder(picked); setRomMsg("Destination set — it'll be used on the next copy."); }
  }

  async function handleDelocalize(): Promise<void> {
    if (!slug) return;
    setRomBusy(true); setRomMsg("");
    const r = await window.emusync.rom.delocalize(slug);
    if (r.ok) { setLocalRomPath(""); setRomMsg("✓ Local copy removed."); }
    else setRomMsg(r.error ?? "Failed to remove local copy.");
    setRomBusy(false);
  }

  function validate(): boolean {
    const e: Record<string, string> = {};
    if (!name.trim()) e.name = "Game name is required.";
    if (!savePath.trim()) e.savePath = "Save file path is required.";
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  async function handleSave(): Promise<void> {
    if (!validate()) return;
    setSaving(true);
    try {
      let finalSlug = slug;
      if (isNew) {
        const game = await addGame(name.trim());
        finalSlug = game.slug;
      } else {
        await updateGame(slug!, name.trim());
      }
      const cfg: GameDeviceConfig = {
        rom_path: romPath.trim(),
        save_path: savePath.trim(),
        launch_command: launchCommand.trim(),
        state_path: statePath.trim(),
        // Preserve the network-ROM source fields the form doesn't edit (#255).
        rom_source: romSource,
        rom_rel_path: netExtraRef.current.rom_rel_path,
        local_rom_path: localRomPath,
        rom_sha256: netExtraRef.current.rom_sha256,
        rom_folder_path: netExtraRef.current.rom_folder_path,
      };
      await setGameDevice(finalSlug!, cfg);
      onSaved();
    } catch (e: unknown) {
      setErrors({ _global: e instanceof Error ? e.message : "Failed to save. Check server connection." });
    } finally {
      setSaving(false);
    }
  }

  async function handlePushSave(): Promise<void> {
    if (!slug || !savePath) return;
    setSaveOp({ status: "busy", action: "push", msg: "" });
    const result = await window.emusync.save.push(slug, savePath);
    if (result.ok) {
      setSaveOp({ status: "ok", action: "push", msg: "Pushed to server" });
      await loadSyncInfo();
      const t = await window.emusync.files.getSaveTime(savePath).catch(() => null);
      setLocalSaveTime(t);
    } else {
      setSaveOp({ status: "error", action: "push", msg: result.error || "Push failed" });
    }
  }

  async function handlePullSave(): Promise<void> {
    if (!slug || !savePath) return;
    setSaveOp({ status: "busy", action: "pull", msg: "" });
    const result = await window.emusync.save.pull(slug, savePath);
    if (result.ok) {
      if (result.pulled) {
        setSaveOp({ status: "ok", action: "pull", msg: "Pulled — previous save backed up to .bak" });
        const t = await window.emusync.files.getSaveTime(savePath).catch(() => null);
        setLocalSaveTime(t);
      } else {
        setSaveOp({ status: "ok", action: "pull", msg: "No server save yet" });
      }
    } else {
      setSaveOp({ status: "error", action: "pull", msg: result.error || "Pull failed" });
    }
  }

  async function handlePushState(): Promise<void> {
    if (!slug || !statePath) return;
    setStateOp({ status: "busy", action: "push", msg: "" });
    const result = await window.emusync.state.push(slug, statePath);
    if (result.ok) {
      setStateOp({ status: "ok", action: "push", msg: "Pushed to server" });
      await loadSyncInfo();
      const latest = await window.emusync.files.getLatestInFolder(statePath).catch(() => null);
      setLatestStateFile(latest);
    } else {
      setStateOp({ status: "error", action: "push", msg: result.error || "Push failed" });
    }
  }

  async function handlePullState(): Promise<void> {
    if (!slug || !statePath) return;
    setStateOp({ status: "busy", action: "pull", msg: "" });
    const result = await window.emusync.state.pull(slug, statePath);
    if (result.ok) {
      if (result.pulled) {
        setStateOp({ status: "ok", action: "pull", msg: "Pulled — previous state backed up to .bak" });
        const latest = await window.emusync.files.getLatestInFolder(statePath).catch(() => null);
        setLatestStateFile(latest);
      } else {
        setStateOp({ status: "ok", action: "pull", msg: "No server state yet" });
      }
    } else {
      setStateOp({ status: "error", action: "pull", msg: result.error || "Pull failed" });
    }
  }

  function opColor(op: SyncOp): string {
    if (op.status === "ok") return "var(--green, #4caf50)";
    if (op.status === "error") return "var(--red, #ef4444)";
    return "var(--text-muted)";
  }

  const showSyncPanel = !isNew && !!savePath;

  return (
    <div>
      <div className="config-header">
        <button className="btn btn-ghost" onClick={onBack}>← Back</button>
        <h2>{isNew ? "Add game" : "Game settings"}</h2>
        {!isNew && onPlay && (
          <button className="btn btn-primary" onClick={() => onPlay(slug!)}>▶ Play</button>
        )}
      </div>

      {loadError && <p className="error-msg" style={{ marginBottom: 16 }}>{loadError}</p>}
      {errors._global && <p className="error-msg" style={{ marginBottom: 16 }}>{errors._global}</p>}

      <div className="card config-form">
        <div className="input-group">
          <label>Game name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={errors.name ? "error" : ""}
            placeholder="The Legend of Zelda: BOTW"
          />
          {errors.name && <span className="error-msg">{errors.name}</span>}
        </div>

        <div className="input-group">
          <label>ROM file <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>(optional)</span></label>
          <div className="input-row">
            <input
              type="text"
              value={romPath}
              onChange={(e) => setRomPath(e.target.value)}
              placeholder="/path/to/game.rom"
            />
            <button className="btn btn-icon" title="Browse" onClick={() => pickFile(setRomPath, "Select ROM file")}>
              📁
            </button>
          </div>
          {romSource === "network" && !isNew && (
            <div style={{ marginTop: 8, padding: "8px 10px", background: "var(--bg-subtle, rgba(127,127,127,0.08))", borderRadius: 6 }}>
              <div style={{ fontSize: 13, marginBottom: 6 }}>
                🌐 Network ROM — {localRomPath
                  ? <>a local copy exists for offline play.</>
                  : <>played from the network share.</>}
              </div>
              {!localRomPath && (
                <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 6, display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                  <span>Local copy folder:</span>
                  <span className="truncate" style={{ maxWidth: 280 }}>{localDestFolder || "not set"}</span>
                  <button className="btn btn-ghost" style={{ fontSize: 11, padding: "1px 8px" }} onClick={handlePickDestFolder}>
                    {localDestFolder ? "Change…" : "Choose…"}
                  </button>
                </div>
              )}
              <div className="input-row" style={{ gap: 8 }}>
                {localRomPath ? (
                  <button className="btn" disabled={romBusy} onClick={handleDelocalize}>
                    Remove offline copy
                  </button>
                ) : (
                  <button className="btn" disabled={romBusy} onClick={handleLocalize}>
                    Copy for offline play
                  </button>
                )}
                {romBusy && <span style={{ fontSize: 13, color: "var(--text-muted)" }}>Working…</span>}
              </div>
              {romMsg && <div style={{ fontSize: 12, marginTop: 6, color: "var(--text-muted)" }}>{romMsg}</div>}
            </div>
          )}
        </div>

        <div className="input-group">
          <label>Save file location</label>
          <div className="input-row">
            <input
              type="text"
              value={savePath}
              onChange={(e) => setSavePath(e.target.value)}
              className={errors.savePath ? "error" : ""}
              placeholder="/path/to/save.sav"
            />
            <button className="btn btn-icon" title="Browse" onClick={() => pickFile(setSavePath, "Select save file")}>
              📁
            </button>
          </div>
          {errors.savePath && <span className="error-msg">{errors.savePath}</span>}
        </div>

        <div className="input-group">
          <label>States folder <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>(optional)</span></label>
          <div className="input-row">
            <input
              type="text"
              value={statePath}
              onChange={(e) => setStatePath(e.target.value)}
              placeholder="/home/user/.config/retroarch/states/GameName"
            />
            <button className="btn btn-icon" title="Browse folder" onClick={async () => {
              const folder = await window.emusync.dialog.openFolder();
              if (folder) setStatePath(folder);
            }}>
              📁
            </button>
          </div>
          <span style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
            The folder where RetroArch stores all save states for this game. All files in the folder are synced.
          </span>
        </div>

        <div className="input-group">
          <label>Launch command <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>(optional)</span></label>
          <input
            type="text"
            value={launchCommand}
            onChange={(e) => setLaunchCommand(e.target.value)}
            placeholder="retroarch -L snes.so %ROM%"
          />
          <span style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
            Use %ROM% as a placeholder for the ROM path.
          </span>
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
            {saving ? <><span className="spinner" /> Saving…</> : "✓ Save"}
          </button>
        </div>
      </div>

      {showSyncPanel && (
        <div className="card" style={{ marginTop: 16 }}>

          {/* ── Save sync ── */}
          <SyncSection
            label="Save"
            pathLine={savePath}
            localLabel="Local"
            localTime={localSaveTime}
            serverTime={serverSaveMeta?.pushed_at ?? null}
            op={saveOp}
            onPush={handlePushSave}
            onPull={handlePullSave}
            pushDisabled={!localSaveTime}
            pullDisabled={!serverSaveMeta}
            opColor={opColor(saveOp)}
          />

          {/* ── State sync ── */}
          <div style={{ borderTop: "1px solid var(--border)", margin: "16px -16px 0" }} />
          <div style={{ paddingTop: 16 }}>
            {statePath ? (
              <SyncSection
                label="Save state"
                pathLine={statePath.endsWith("/") ? statePath : statePath + "/"}
                localLabel="Local (latest)"
                localTime={latestStateFile?.time ?? null}
                serverTime={serverStateMeta?.pushed_at ?? null}
                op={stateOp}
                onPush={handlePushState}
                onPull={handlePullState}
                pushDisabled={!latestStateFile}
                pullDisabled={!serverStateMeta}
                opColor={opColor(stateOp)}
              />
            ) : (
              <div>
                <div style={{ fontWeight: 600, fontSize: 12, marginBottom: 8, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                  Save state
                </div>
                <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
                  No state file configured — set one above to enable state sync.
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── shared sync section component ─────────────────────────────────────────────

function SyncSection({
  label,
  pathLine,
  localLabel,
  localTime,
  serverTime,
  op,
  onPush,
  onPull,
  pushDisabled,
  pullDisabled,
  opColor,
}: {
  label: string;
  pathLine: string;
  localLabel: string;
  localTime: string | null;
  serverTime: string | null;
  op: SyncOp;
  onPush: () => void;
  onPull: () => void;
  pushDisabled: boolean;
  pullDisabled: boolean;
  opColor: string;
}): React.ReactElement {
  const busy = op.status === "busy";

  function SyncBtn({ action, onClick, disabled, children }: {
    action: "push" | "pull"; onClick: () => void; disabled: boolean; children: React.ReactNode;
  }): React.ReactElement {
    const isActive = busy && op.action === action;
    return (
      <button
        className="btn btn-ghost"
        style={{ fontSize: 12, padding: "3px 10px", minWidth: 72 }}
        disabled={busy || disabled}
        onClick={onClick}
      >
        {isActive ? <span className="spinner" style={{ width: 10, height: 10 }} /> : children}
      </button>
    );
  }

  return (
    <div>
      <div style={{
        fontWeight: 600, fontSize: 12, marginBottom: 10,
        color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em",
      }}>
        {label}
      </div>
      <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 10, wordBreak: "break-all" }}>
        {pathLine}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: "8px 12px", alignItems: "center" }}>
        <span style={{ fontSize: 13 }}>
          <span style={{ color: "var(--text-muted)" }}>{localLabel}: </span>
          <strong><RelTime iso={localTime} /></strong>
        </span>
        <SyncBtn action="push" onClick={onPush} disabled={pushDisabled}>↑ Push</SyncBtn>

        <span style={{ fontSize: 13 }}>
          <span style={{ color: "var(--text-muted)" }}>Server: </span>
          <strong><RelTime iso={serverTime} /></strong>
        </span>
        <SyncBtn action="pull" onClick={onPull} disabled={pullDisabled}>↓ Pull</SyncBtn>
      </div>
      {op.status !== "idle" && op.status !== "busy" && (
        <div style={{ marginTop: 8, fontSize: 12, color: opColor }}>{op.msg}</div>
      )}
    </div>
  );
}
