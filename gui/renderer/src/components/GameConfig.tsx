import React, { useEffect, useState } from "react";
import { addGame, getGameDevice, setGameDevice, updateGame, type GameDeviceConfig } from "../api";

type Props = {
  slug: string | null;
  name?: string;
  onBack: () => void;
  onSaved: () => void;
  onPlay?: (slug: string) => void;
};

export default function GameConfig({ slug, name: initialName, onBack, onSaved, onPlay }: Props): React.ReactElement {
  const isNew = slug === null;
  const [name, setName] = useState(initialName ?? "");
  const [romPath, setRomPath] = useState("");
  const [savePath, setSavePath] = useState("");
  const [launchCommand, setLaunchCommand] = useState("");
  const [console, setConsole] = useState("");
  const [statePath, setStatePath] = useState("");
  const [romFolderPath, setRomFolderPath] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    if (!slug) return;
    getGameDevice(slug)
      .then((cfg) => {
        setRomPath(cfg.rom_path);
        setSavePath(cfg.save_path);
        setLaunchCommand(cfg.launch_command);
        setConsole(cfg.console || "");
        setStatePath(cfg.state_path || "");
        setRomFolderPath(cfg.rom_folder_path || "");
      })
      .catch(() => setLoadError("Could not load device config — the server may be unreachable."));
  }, [slug]);

  async function pickFile(setter: (p: string) => void, title: string): Promise<void> {
    const path = await window.emusync.dialog.openFile({ title });
    if (path) setter(path);
  }

  function validate(): boolean {
    const e: Record<string, string> = {};
    if (!name.trim()) e.name = "Game name is required.";
    if (!savePath.trim()) e.savePath = "Save file path is required.";
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  async function save(): Promise<void> {
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
        console: console.trim(),
        state_path: statePath.trim(),
        rom_folder_path: romFolderPath.trim(),
      };
      await setGameDevice(finalSlug!, cfg);
      onSaved();
    } catch (e: unknown) {
      setErrors({ _global: e instanceof Error ? e.message : "Failed to save. Check server connection." });
    } finally {
      setSaving(false);
    }
  }

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
          <label>Console <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>(optional)</span></label>
          <input
            type="text"
            value={console}
            onChange={(e) => setConsole(e.target.value)}
            placeholder="GBA, PSX, NDS, SNES, etc."
          />
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
          <button className="btn btn-primary" onClick={save} disabled={saving}>
            {saving ? <><span className="spinner" /> Saving…</> : "✓ Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
