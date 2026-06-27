import React, { useCallback, useEffect, useRef, useState } from "react";
import { addGame, getGame, getGameDevice, getDeviceConsoles, getSaveMeta, getStateMeta, removeGame, setGameDevice, updateGame, whoami, type GameDeviceConfig, type SaveMeta } from "../api";
import { RelTime } from "../time";

type Props = {
  slug: string | null;
  name?: string;
  onBack: () => void;
  onSaved: () => void;
  onPlay?: (slug: string) => void;
  embedded?: boolean;            // rendered inside the tabbed game modal (#260)
  onRemoved?: () => void;        // game deleted from the Settings tab
};

type SyncOp = { status: "idle" | "busy" | "ok" | "error"; action: "push" | "pull" | null; msg: string };
const IDLE_OP: SyncOp = { status: "idle", action: null, msg: "" };



export default function GameConfig({ slug, name: initialName, onBack, onSaved, onPlay, embedded, onRemoved }: Props): React.ReactElement {
  const isNew = slug === null;
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);
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

  async function handleDelete(): Promise<void> {
    if (!slug) return;
    setDeleting(true);
    try {
      await removeGame(slug);
      onRemoved?.();
    } catch (e: unknown) {
      setErrors({ _global: e instanceof Error ? e.message : "Failed to delete game." });
      setDeleting(false);
      setDeleteConfirm(false);
    }
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


  const showSyncPanel = !isNew && !!savePath;

  return (
    <div>
      {!embedded && (
        <div className="config-header">
          <button className="btn btn-ghost" onClick={onBack}>← Back</button>
          <h2>{isNew ? "Add game" : "Game settings"}</h2>
          {!isNew && onPlay && (
            <button className="btn btn-primary" onClick={() => onPlay(slug!)}>▶ Play</button>
          )}
        </div>
      )}

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
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontSize: 13, minWidth: 0 }}>
                  🌐 Network ROM — {localRomPath
                    ? <>local copy ready for offline play.</>
                    : <>played from the network share.</>}
                </span>
                {localRomPath ? (
                  <button className="btn" disabled={romBusy} onClick={handleDelocalize} style={{ flexShrink: 0 }}>Remove offline copy</button>
                ) : (
                  <>
                    <button className="btn" disabled={romBusy} onClick={handleLocalize} style={{ flexShrink: 0 }}>Copy for offline play</button>
                    <button
                      className="btn btn-ghost"
                      style={{ flexShrink: 0 }}
                      onClick={handlePickDestFolder}
                      title={localDestFolder ? `Local copies go to: ${localDestFolder}` : "Choose where local copies are saved"}
                    >
                      {localDestFolder ? "Change folder…" : "Choose folder…"}
                    </button>
                  </>
                )}
                {romBusy && <span style={{ fontSize: 13, color: "var(--text-muted)", flexShrink: 0 }}>Working…</span>}
                {!romBusy && romMsg && <span style={{ fontSize: 13, color: "var(--text-muted)", flexShrink: 0 }}>{romMsg}</span>}
              </div>
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
          {showSyncPanel && (
            <SyncLine
              localTime={localSaveTime}
              serverTime={serverSaveMeta?.pushed_at ?? null}
              op={saveOp}
              onPush={handlePushSave}
              onPull={handlePullSave}
              pushDisabled={!localSaveTime}
              pullDisabled={!serverSaveMeta}
            />
          )}
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
          {!isNew && statePath && (
            <SyncLine
              localTime={latestStateFile?.time ?? null}
              serverTime={serverStateMeta?.pushed_at ?? null}
              op={stateOp}
              onPush={handlePushState}
              onPull={handlePullState}
              pushDisabled={!latestStateFile}
              pullDisabled={!serverStateMeta}
            />
          )}
        </div>

        <div className="input-group">
          <label>Launch command <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>(optional)</span></label>
          <input
            type="text"
            value={launchCommand}
            onChange={(e) => setLaunchCommand(e.target.value)}
            placeholder="retroarch -L snes.so %ROM%"
          />
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
          <div>
            {!isNew && (deleteConfirm ? (
              <span style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 13 }}>
                Delete this game?
                <button className="btn btn-danger" onClick={handleDelete} disabled={deleting}>
                  {deleting ? <><span className="spinner" /> Deleting…</> : "Yes, delete"}
                </button>
                <button className="btn btn-ghost" onClick={() => setDeleteConfirm(false)} disabled={deleting}>Cancel</button>
              </span>
            ) : (
              <button className="btn btn-danger" onClick={() => setDeleteConfirm(true)}>🗑 Delete</button>
            ))}
          </div>
          <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
            {saving ? <><span className="spinner" /> Saving…</> : "✓ Save"}
          </button>
        </div>
      </div>

    </div>
  );
}

// ── shared sync section component ─────────────────────────────────────────────

// Compact one-line sync row shown under a save/state location field (#264):
//   Sync: 💾 <local> · ☁ <server>            [↑ Push] [↓ Pull]
// The Push/Pull buttons flash ✓/✗ briefly on result instead of a status line.
function SyncLine({
  localTime, serverTime, op, onPush, onPull, pushDisabled, pullDisabled,
}: {
  localTime: string | null;
  serverTime: string | null;
  op: SyncOp;
  onPush: () => void;
  onPull: () => void;
  pushDisabled: boolean;
  pullDisabled: boolean;
}): React.ReactElement {
  const busy = op.status === "busy";
  const [flash, setFlash] = useState<{ action: "push" | "pull"; ok: boolean } | null>(null);
  useEffect(() => {
    if ((op.status === "ok" || op.status === "error") && op.action) {
      setFlash({ action: op.action, ok: op.status === "ok" });
      const t = setTimeout(() => setFlash(null), 1800);
      return () => clearTimeout(t);
    }
  }, [op.status, op.action]);

  function Btn({ action, onClick, disabled, label }: {
    action: "push" | "pull"; onClick: () => void; disabled: boolean; label: string;
  }): React.ReactElement {
    const showSpinner = busy && op.action === action;
    const f = flash?.action === action ? flash : null;
    return (
      <button
        className="btn btn-ghost"
        style={{ fontSize: 12, padding: "3px 10px", minWidth: 64, color: f ? (f.ok ? "var(--green)" : "var(--red)") : undefined }}
        disabled={busy || disabled}
        onClick={onClick}
        title={op.action === action && op.status === "error" ? op.msg : undefined}
      >
        {showSpinner ? <span className="spinner" style={{ width: 10, height: 10 }} /> : f ? (f.ok ? "✓" : "✗") : label}
      </button>
    );
  }

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 6, fontSize: 13, flexWrap: "wrap" }}>
      <span style={{ color: "var(--text-muted)", fontSize: 12 }}>Sync:</span>
      <span title="On this device"><span style={{ opacity: 0.7 }}>💾</span> <RelTime iso={localTime} /></span>
      <span style={{ color: "var(--text-muted)" }}>·</span>
      <span title="On the server"><span style={{ opacity: 0.7 }}>☁️</span> <RelTime iso={serverTime} /></span>
      <span style={{ flex: 1 }} />
      <Btn action="push" onClick={onPush} disabled={pushDisabled} label="↑ Push" />
      <Btn action="pull" onClick={onPull} disabled={pullDisabled} label="↓ Pull" />
    </div>
  );
}
