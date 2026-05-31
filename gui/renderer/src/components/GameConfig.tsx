import React, { useCallback, useEffect, useState } from "react";
import { addGame, getGameDevice, getSaveMeta, getStateMeta, setGameDevice, updateGame, type GameDeviceConfig, type SaveMeta } from "../api";

type Props = {
  slug: string | null;
  name?: string;
  onBack: () => void;
  onSaved: () => void;
  onPlay?: (slug: string) => void;
};

type SyncOp = { status: "idle" | "busy" | "ok" | "error"; action: "push" | "pull" | null; msg: string };
const IDLE_OP: SyncOp = { status: "idle", action: null, msg: "" };

function fmtTime(t: string | null | undefined): string {
  if (!t) return "—";
  return t.replace("T", " ").slice(0, 19);
}

function parentDir(filePath: string): string {
  const idx = filePath.lastIndexOf("/");
  return idx > 0 ? filePath.slice(0, idx) : filePath;
}

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

  useEffect(() => {
    if (!slug) return;
    getGameDevice(slug)
      .then((cfg) => {
        setRomPath(cfg.rom_path);
        setSavePath(cfg.save_path);
        setStatePath(cfg.state_path ?? "");
        setLaunchCommand(cfg.launch_command);
      })
      .catch(() => setLoadError("Could not load device config — the server may be unreachable."));
  }, [slug]);

  const loadSyncInfo = useCallback(async () => {
    if (!slug) return;
    const [sm, ss] = await Promise.allSettled([getSaveMeta(slug), getStateMeta(slug)]);
    if (sm.status === "fulfilled") setServerSaveMeta(sm.value);
    if (ss.status === "fulfilled") setServerStateMeta(ss.value);
  }, [slug]);

  useEffect(() => {
    if (!savePath) return;
    (window as any).emusync.files.getSaveTime(savePath).then(setLocalSaveTime).catch(() => {});
  }, [savePath]);

  useEffect(() => {
    if (!statePath) return;
    const dir = parentDir(statePath);
    (window as any).emusync.files.getLatestInFolder(dir).then(setLatestStateFile).catch(() => {});
  }, [statePath]);

  useEffect(() => { loadSyncInfo(); }, [loadSyncInfo]);

  async function pickFile(setter: (p: string) => void, title: string): Promise<void> {
    const path = await (window as any).emusync.dialog.openFile({ title });
    if (path) setter(path);
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
    const result = await (window as any).emusync.save.push(slug, savePath);
    if (result.ok) {
      setSaveOp({ status: "ok", action: "push", msg: "Pushed to server" });
      await loadSyncInfo();
      const t = await (window as any).emusync.files.getSaveTime(savePath).catch(() => null);
      setLocalSaveTime(t);
    } else {
      setSaveOp({ status: "error", action: "push", msg: result.error || "Push failed" });
    }
  }

  async function handlePullSave(): Promise<void> {
    if (!slug || !savePath) return;
    setSaveOp({ status: "busy", action: "pull", msg: "" });
    const result = await (window as any).emusync.save.pull(slug, savePath);
    if (result.ok) {
      if (result.pulled) {
        setSaveOp({ status: "ok", action: "pull", msg: "Pulled — previous save backed up to .bak" });
        const t = await (window as any).emusync.files.getSaveTime(savePath).catch(() => null);
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
    const result = await (window as any).emusync.state.push(slug, statePath);
    if (result.ok) {
      setStateOp({ status: "ok", action: "push", msg: "Pushed to server" });
      await loadSyncInfo();
      const dir = parentDir(statePath);
      const latest = await (window as any).emusync.files.getLatestInFolder(dir).catch(() => null);
      setLatestStateFile(latest);
    } else {
      setStateOp({ status: "error", action: "push", msg: result.error || "Push failed" });
    }
  }

  async function handlePullState(): Promise<void> {
    if (!slug || !statePath) return;
    setStateOp({ status: "busy", action: "pull", msg: "" });
    const result = await (window as any).emusync.state.pull(slug, statePath);
    if (result.ok) {
      if (result.pulled) {
        setStateOp({ status: "ok", action: "pull", msg: "Pulled — previous state backed up to .bak" });
        const dir = parentDir(statePath);
        const latest = await (window as any).emusync.files.getLatestInFolder(dir).catch(() => null);
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

          {/* ── State sync (only when state_path is configured) ── */}
          {statePath && (
            <>
              <div style={{ borderTop: "1px solid var(--border)", margin: "16px -16px 0" }} />
              <div style={{ paddingTop: 16 }}>
                <SyncSection
                  label="Save state"
                  pathLine={parentDir(statePath) + "/"}
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
              </div>
            </>
          )}
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
          <strong>{fmtTime(localTime)}</strong>
        </span>
        <SyncBtn action="push" onClick={onPush} disabled={pushDisabled}>↑ Push</SyncBtn>

        <span style={{ fontSize: 13 }}>
          <span style={{ color: "var(--text-muted)" }}>Server: </span>
          <strong>{fmtTime(serverTime)}</strong>
        </span>
        <SyncBtn action="pull" onClick={onPull} disabled={pullDisabled}>↓ Pull</SyncBtn>
      </div>
      {op.status !== "idle" && op.status !== "busy" && (
        <div style={{ marginTop: 8, fontSize: 12, color: opColor }}>{op.msg}</div>
      )}
    </div>
  );
}
