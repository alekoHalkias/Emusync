import React, { useEffect, useState } from "react";
import { addGame, setGameDevice, listGames, getGameDevice, type Game } from "../api";

type ConsoleOption = { key: string; label: string };

type EmulatorOption = {
  id: string;
  label: string;
  execPath: string;
  saveDir: string;
  corePath?: string;
  coreFolderName?: string;
  romDirs: string[];
};

type RomEntry = {
  name: string;
  romPath: string;
  romFileName: string;
  savePath: string;
  saveExists: boolean;
  launchCommand: string;
  consoleName?: string;
  coreName?: string;
  statePath?: string;
  stateExists?: boolean;
  existingGameSlug?: string;
  romFolderPath?: string;
  linkedSlug?: string;
  linkedName?: string;
};

type Phase =
  | "console"    // select console
  | "detecting"  // scanning for installed emulators
  | "emulator"   // pick emulator (or no-emulator message)
  | "scanning"   // scanning ROMs + saves
  | "results"    // ROM list with checkboxes
  | "importing"  // import in progress
  | "done";      // finished

type Props = { onClose: () => void; onImported: () => void };

const STEP_LABELS = ["Console", "Emulator", "ROMs"];

function stepIndex(phase: Phase): number {
  if (phase === "console" || phase === "detecting") return 0;
  if (phase === "emulator") return 1;
  return 2;
}

function getConsoleAbbreviation(consoleKey: string): string {
  const map: Record<string, string> = {
    gba: "GBA",
    gb: "GB",
    snes: "SNES",
    nes: "NES",
    n64: "N64",
    nds: "NDS",
    genesis: "Genesis",
    sms: "SMS",
    pce: "PCE",
    psx: "PSX",
  };
  return map[consoleKey] || consoleKey.toUpperCase();
}

export default function ConsoleImport({ onClose, onImported }: Props): React.ReactElement {
  const [phase, setPhase]         = useState<Phase>("console");
  const [consoles, setConsoles]   = useState<ConsoleOption[]>([]);
  const [consoleSel, setConsoleSel] = useState("");
  const [emulators, setEmulators] = useState<EmulatorOption[]>([]);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [emuSel, setEmuSel]       = useState<EmulatorOption | null>(null);
  const [extraPaths, setExtraPaths] = useState<string[]>([]);
  const [romDirs, setRomDirs]     = useState<string[]>([]);
  const [removedDirs, setRemovedDirs] = useState<Set<string>>(new Set());
  const [roms, setRoms]           = useState<RomEntry[]>([]);
  const [selected, setSelected]   = useState<Set<string>>(new Set());
  const [names, setNames]         = useState<Record<string, string>>({});
  const [error, setError]         = useState("");
  const [progress, setProgress]   = useState({ done: 0, total: 0 });
  const [importErrors, setImportErrors] = useState<string[]>([]);
  const [savedFolders, setSavedFolders] = useState<string[]>([]);

  useEffect(() => {
    (window as any).emusync.emulator.consoles().then(setConsoles);
  }, []);

  async function detectEmulators(): Promise<void> {
    setPhase("detecting");
    try {
      const [{ options, suggestions: sugg }, saved] = await Promise.all([
        (window as any).emusync.emulator.detect(consoleSel),
        (window as any).emusync.config.getRecentFolders(consoleSel),
      ]);
      setEmulators(options);
      setSuggestions(sugg);
      setSavedFolders(saved);
      setExtraPaths(saved);
      if (options.length === 1) setEmuSel(options[0]);
      setPhase("emulator");
    } catch {
      setEmulators([]);
      setPhase("emulator");
    }
  }

  async function scanRoms(paths: string[]): Promise<void> {
    if (!emuSel) return;
    setPhase("scanning");
    setError("");
    try {
      const result = await (window as any).emusync.emulator.scan(consoleSel, emuSel, paths);

      // Extract ROM filename from path (without extension)
      const getRomFileName = (path: string): string => {
        const filename = path.split("/").pop() || "";
        return filename.replace(/\.[^.]+$/, "").toLowerCase();
      };

      // Annotate each ROM with folder path (always)
      // Find the source folder that contains this ROM
      const annotated: RomEntry[] = result.roms.map((rom: RomEntry) => {
        let romFolderPath = "/";

        // Try to match to selected paths first (for consistency)
        for (const path of paths) {
          const normalizedPath = path.replace(/\/$/, "");
          const normalizedRom = rom.romPath.replace(/\/$/, "");
          if (normalizedRom.startsWith(normalizedPath + "/") || normalizedRom === normalizedPath) {
            romFolderPath = normalizedPath;
            break;
          }
        }

        // If no match found in selected paths, try romDirs from scan results
        if (romFolderPath === "/" && result.romDirs && result.romDirs.length > 0) {
          for (const dir of result.romDirs) {
            const normalizedDir = dir.replace(/\/$/, "");
            const normalizedRom = rom.romPath.replace(/\/$/, "");
            if (normalizedRom.startsWith(normalizedDir + "/") || normalizedRom === normalizedDir) {
              romFolderPath = normalizedDir;
              break;
            }
          }
        }

        // Last resort: extract parent directory from ROM path
        if (romFolderPath === "/") {
          romFolderPath = rom.romPath.replace(/[^/]+$/, "").replace(/\/$/, "") || "/";
        }

        return {
          ...rom,
          romFileName: getRomFileName(rom.romPath),
          romFolderPath,
        };
      });

      // Dedup: filter already-imported ROMs; detect cross-device links.
      let newRoms = annotated;
      try {
        const existingGames = await listGames();

        // Collect this-device configs (404 = game exists on server but not this device)
        const thisDeviceConfigs: Array<{ slug: string; romPath: string }> = [];
        for (const g of existingGames) {
          try {
            const config = await getGameDevice(g.slug);
            if (config.rom_path) {
              thisDeviceConfigs.push({ slug: g.slug, romPath: config.rom_path });
            }
          } catch {
            // 404 = game known to server but not configured on this device — candidate for linking
          }
        }

        // Build slug→name map for all server games (for cross-device badge label)
        const allGamesBySlug: Record<string, string> = {};
        for (const g of existingGames) allGamesBySlug[g.slug] = g.name;

        const withMatches = annotated.map((rom: RomEntry) => {
          // 1. Already on this device → skip
          const thisMatch = thisDeviceConfigs.find(cfg =>
            cfg.romPath === rom.romPath || getRomFileName(cfg.romPath) === rom.romFileName
          );
          if (thisMatch) return { ...rom, existingGameSlug: thisMatch.slug };

          // 2. Exists on another device → link candidate (match by slug or name)
          const slugified = rom.romFileName.replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
          const crossMatch = existingGames.find(g => {
            if (allGamesBySlug[g.slug] === undefined) return false;
            const nameSlug = g.name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
            return g.slug === slugified || nameSlug === slugified ||
              g.name.toLowerCase() === rom.name.toLowerCase();
          });
          if (crossMatch) return { ...rom, linkedSlug: crossMatch.slug, linkedName: crossMatch.name };

          return rom;
        });

        newRoms = withMatches.filter((rom: RomEntry) => !rom.existingGameSlug);
        const skipCount = withMatches.length - newRoms.length;
        if (skipCount > 0 && newRoms.length === 0) {
          setError(`${skipCount} ROM${skipCount !== 1 ? "s" : ""} found — all already imported on this device.`);
        }
      } catch {
        // Dedup unavailable (server not reachable / not paired yet) — show all ROMs
      }

      setRoms(newRoms);
      setRomDirs(result.romDirs ?? []);
      setSelected(new Set(newRoms.map((r: RomEntry) => r.romPath)));
      setPhase("results");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Scan failed.");
      setPhase("results");
    }
  }

  async function addExtraPath(): Promise<void> {
    const folder = await (window as any).emusync.dialog.openFolder();
    if (!folder) return;
    if (extraPaths.includes(folder)) return;
    await (window as any).emusync.config.addRecentFolder(consoleSel, folder);
    const updated = [...extraPaths, folder];
    setSavedFolders(updated);
    setExtraPaths(updated);
    scanRoms(updated);
  }

  async function removeExtraPath(path: string): Promise<void> {
    const updated = extraPaths.filter(p => p !== path);
    setSavedFolders(updated);
    setExtraPaths(updated);
    const cfg = await (window as any).emusync.config.load();
    if (!cfg.recent_import_folders) cfg.recent_import_folders = {};
    cfg.recent_import_folders[consoleSel] = updated;
    await (window as any).emusync.config.save(cfg);
    scanRoms(updated);
  }

  function removeRomDir(path: string): void {
    // Find which ROMs to remove
    const romsToRemove = roms.filter(r => r.romFolderPath === path);

    // Remove ROMs from this folder
    setRoms(prev => prev.filter(r => r.romFolderPath !== path));
    setSelected(prev => {
      const next = new Set(prev);
      romsToRemove.forEach(r => next.delete(r.romPath));
      return next;
    });
  }

  function toggleRom(romPath: string): void {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(romPath) ? next.delete(romPath) : next.add(romPath);
      return next;
    });
  }

  function toggleAll(paths: string[]): void {
    const allOn = paths.every(p => selected.has(p));
    setSelected(prev => {
      const next = new Set(prev);
      allOn ? paths.forEach(p => next.delete(p)) : paths.forEach(p => next.add(p));
      return next;
    });
  }

  async function doImport(): Promise<void> {
    const toImport = roms.filter(r => selected.has(r.romPath));
    setProgress({ done: 0, total: toImport.length });
    setImportErrors([]);
    setPhase("importing");
    const errs: string[] = [];
    const consoleAbbr = getConsoleAbbreviation(consoleSel);
    for (let i = 0; i < toImport.length; i++) {
      const rom = toImport[i];
      try {
        const displayName = names[rom.romPath] ?? rom.name;

        // ── Organise ROM into a per-game subfolder if it sits directly in
        //    the scan root.  RetroArch mirrors the folder structure into
        //    saves/states, so moving the ROM first ensures saves land in
        //    the correct per-game subfolder automatically.
        let romPath      = rom.romPath;
        let savePath     = rom.savePath;
        let statePath    = rom.statePath ?? "";
        let launchCmd    = rom.launchCommand;
        const scanRoot   = (rom.romFolderPath ?? "").replace(/\/$/, "");
        const romParent  = romPath.includes("/") ? romPath.substring(0, romPath.lastIndexOf("/")) : "";
        if (scanRoot && romParent === scanRoot) {
          const moved = await (window as any).emusync.files.moveToSubfolder({
            romPath, subfolderName: rom.name,
            newSavePath: savePath,        // scan already returned the canonical target path
            newStateFolder: statePath,    // scan already returned the canonical state folder
          });
          if (moved.ok) {
            launchCmd  = launchCmd.replaceAll(romPath, moved.newRomPath);
            romPath    = moved.newRomPath;
            savePath   = moved.newSavePath;
            statePath  = moved.newStateFolder;
          }
        }

        const slug = rom.linkedSlug ?? (await addGame(displayName, consoleAbbr)).slug;
        await setGameDevice(slug, {
          rom_path: romPath,
          save_path: savePath,
          launch_command: launchCmd,
          state_path: statePath,
          rom_folder_path: scanRoot || rom.romFolderPath || "",
        });
      } catch { errs.push(names[rom.romPath] ?? rom.name); }
      setProgress({ done: i + 1, total: toImport.length });
    }
    setImportErrors(errs);
    setPhase("done");
  }

  // Group ROMs by parent directory
  const grouped: Record<string, RomEntry[]> = {};
  for (const rom of roms) {
    const dir = rom.romPath.replace(/[^/]+$/, "").replace(/\/$/, "") || "/";
    (grouped[dir] = grouped[dir] ?? []).push(rom);
  }
  const selectedCount = roms.filter(r => selected.has(r.romPath)).length;
  const consoleLabel  = consoles.find(c => c.key === consoleSel)?.label ?? "";
  const currentStep   = stepIndex(phase);
  const showStepper   = phase !== "importing" && phase !== "done";

  // Merge auto-detected dirs + extra dirs for display (no dupes, extras marked removable)
  // Filter out any directories the user has removed
  const allRomDirs = [...new Set([...romDirs, ...extraPaths])].filter(p => !removedDirs.has(p));

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal"
        style={{ width: 640, maxHeight: "85vh", display: "flex", flexDirection: "column" }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <h3 style={{ margin: 0 }}>Add console</h3>
          <button className="btn btn-ghost" onClick={onClose}>✕</button>
        </div>

        {/* Step indicator */}
        {showStepper && (
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 20, fontSize: 12 }}>
            {STEP_LABELS.map((label, i) => {
              const active = i === currentStep;
              const done   = i < currentStep;
              return (
                <React.Fragment key={label}>
                  {i > 0 && <span style={{ color: "var(--text-muted)" }}>›</span>}
                  <span style={{
                    color: active ? "var(--accent, #7c8cf8)" : done ? "var(--green, #4caf50)" : "var(--text-muted)",
                    fontWeight: active ? 600 : 400,
                  }}>
                    {done ? `✓ ${label}` : label}
                  </span>
                </React.Fragment>
              );
            })}
          </div>
        )}

        {/* ── console ──────────────────────────────────────────────────────── */}
        {phase === "console" && (
          <>
            <div className="input-group" style={{ marginBottom: 24 }}>
              <label>Select a console</label>
              <select
                value={consoleSel}
                onChange={e => setConsoleSel(e.target.value)}
                style={{ width: "100%" }}
              >
                <option value="">— choose a console —</option>
                {consoles.map(c => (
                  <option key={c.key} value={c.key}>{c.label}</option>
                ))}
              </select>
            </div>
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
              <button className="btn btn-primary" disabled={!consoleSel} onClick={detectEmulators}>
                Next →
              </button>
            </div>
          </>
        )}

        {/* ── detecting ────────────────────────────────────────────────────── */}
        {phase === "detecting" && (
          <div style={{ textAlign: "center", padding: "40px 0" }}>
            <span className="spinner" style={{ width: 28, height: 28 }} />
            <p style={{ marginTop: 16, color: "var(--text-muted)" }}>
              Looking for compatible emulators…
            </p>
          </div>
        )}

        {/* ── emulator ─────────────────────────────────────────────────────── */}
        {phase === "emulator" && (
          <>
            {emulators.length === 0 ? (
              <div style={{ padding: "24px 0", textAlign: "center" }}>
                <div style={{ fontSize: 36, marginBottom: 12 }}>🎮</div>
                <p style={{ fontWeight: 600, marginBottom: 8 }}>
                  No compatible emulator found
                </p>
                <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: suggestions.length ? 12 : 0 }}>
                  Please install a compatible emulator for <strong>{consoleLabel}</strong>.
                </p>
                {suggestions.length > 0 && (
                  <div style={{ fontSize: 12, color: "var(--text-muted)", textAlign: "left",
                    display: "inline-block", marginTop: 4 }}>
                    {suggestions.map(s => <div key={s}>• {s}</div>)}
                  </div>
                )}
              </div>
            ) : (
              <>
                <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 12 }}>
                  Select the emulator to use for <strong>{consoleLabel}</strong>:
                </p>
                <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 16 }}>
                  {emulators.map(emu => (
                    <label
                      key={emu.id}
                      style={{
                        display: "flex", alignItems: "flex-start", gap: 10,
                        padding: "10px 14px",
                        border: `1px solid ${emuSel?.id === emu.id ? "var(--accent, #7c8cf8)" : "var(--border)"}`,
                        borderRadius: 6, cursor: "pointer",
                        background: emuSel?.id === emu.id ? "rgba(124,140,248,0.08)" : "transparent",
                      }}
                    >
                      <input
                        type="radio" name="emulator" value={emu.id}
                        checked={emuSel?.id === emu.id}
                        onChange={() => setEmuSel(emu)}
                        style={{ marginTop: 3 }}
                      />
                      <div>
                        <div style={{ fontWeight: 500, fontSize: 13 }}>{emu.label}</div>
                        <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
                          Saves: {emu.saveDir}
                        </div>
                      </div>
                    </label>
                  ))}
                </div>
              </>
            )}
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => {
                setEmulators([]); setEmuSel(null); setSuggestions([]);  setPhase("console");
              }}>← Back</button>
              {emulators.length === 0 ? (
                <button className="btn btn-ghost" onClick={onClose}>Close</button>
              ) : (
                <button
                  className="btn btn-primary"
                  disabled={!emuSel}
                  onClick={() => scanRoms(extraPaths)}
                >
                  Scan for ROMs →
                </button>
              )}
            </div>
          </>
        )}

        {/* ── scanning ─────────────────────────────────────────────────────── */}
        {phase === "scanning" && (
          <div style={{ textAlign: "center", padding: "40px 0" }}>
            <span className="spinner" style={{ width: 28, height: 28 }} />
            <p style={{ marginTop: 16, color: "var(--text-muted)" }}>
              Scanning for ROMs and saves…
            </p>
          </div>
        )}

        {/* ── results ──────────────────────────────────────────────────────── */}
        {phase === "results" && (
          <>
            {error && <p className="error-msg" style={{ marginBottom: 12 }}>{error}</p>}

            {/* ROM folder list */}
            <div style={{ marginBottom: 12 }}>
              <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontSize: 13, fontWeight: 500 }}>ROM folders</span>
                <button
                  className="btn btn-ghost"
                  style={{ fontSize: 12, padding: "2px 10px" }}
                  onClick={addExtraPath}
                >
                  + Add folder
                </button>
              </div>
              {allRomDirs.length === 0 && (
                <p style={{ fontSize: 12, color: "var(--text-muted)", margin: 0 }}>
                  No ROM folder detected — add one above.
                </p>
              )}
              {allRomDirs.map(p => (
                <div key={p} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, marginBottom: 4 }}>
                  <span style={{ flex: 1, color: "var(--text-muted)", overflow: "hidden",
                    textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {p}
                    {!extraPaths.includes(p) && !removedDirs.has(p) && (
                      <span style={{ fontSize: 11, color: "var(--text-muted)" }}> (detected)</span>
                    )}
                  </span>
                  {!removedDirs.has(p) && (
                    <button
                      className="btn btn-ghost"
                      style={{ fontSize: 11, padding: "1px 6px" }}
                      onClick={() => extraPaths.includes(p) ? removeExtraPath(p) : removeRomDir(p)}
                      title={extraPaths.includes(p) ? "Remove folder" : "Ignore this folder"}
                    >✕</button>
                  )}
                </div>
              ))}
            </div>

            {/* ROM list header with bulk select */}
            {roms.length > 0 && (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
                <span style={{ fontSize: 13, color: "var(--text-muted)" }}>
                  {selectedCount} of {roms.length} selected
                </span>
                <button
                  className="btn btn-ghost"
                  style={{ fontSize: 12, padding: "2px 10px" }}
                  onClick={() => toggleAll(roms.map(r => r.romPath))}
                >
                  {selectedCount === roms.length ? "Deselect all" : "Select all"}
                </button>
              </div>
            )}

            {/* ROM list */}
            <div style={{ flex: 1, overflowY: "auto", border: "1px solid var(--border)", borderRadius: 6 }}>
              {roms.length === 0 ? (
                <div style={{ padding: 24, textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>
                  No ROMs found. Try adding a folder above.
                </div>
              ) : Object.entries(grouped).map(([dir, dirRoms]) => (
                    <React.Fragment key={dir}>
                    {dirRoms.map(rom => (
                      <div
                        key={rom.romPath}
                        style={{
                          display: "flex", alignItems: "flex-start", gap: 10,
                          padding: "10px 12px", borderBottom: "1px solid var(--border)",
                          cursor: "pointer",
                        }}
                        onClick={() => toggleRom(rom.romPath)}
                      >
                        <input
                          type="checkbox"
                          checked={selected.has(rom.romPath)}
                          onChange={() => toggleRom(rom.romPath)}
                          onClick={e => e.stopPropagation()}
                          style={{ marginTop: 3, flexShrink: 0 }}
                        />
                        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 4 }}>
                          <input
                            type="text"
                            value={names[rom.romPath] ?? rom.name}
                            onChange={(e) => setNames({ ...names, [rom.romPath]: e.target.value })}
                            onClick={(e) => e.stopPropagation()}
                            style={{ fontSize: 13, fontWeight: 500, width: "100%" }}
                          />
                          <div style={{ fontSize: 11, color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {rom.romPath}
                          </div>
                          <div style={{ fontSize: 11, color: "var(--text-muted)", display: "flex", gap: 8, alignItems: "center" }}>
                            {rom.saveExists && (
                              <span style={{ color: "var(--green, #4caf50)" }}>✓ Save found</span>
                            )}
                            {rom.statePath && rom.stateExists && (
                              <span style={{ color: "var(--green, #4caf50)" }}>✓ State found</span>
                            )}
                            {rom.linkedSlug && (
                              <span style={{ color: "var(--accent, #7c8cf8)" }}>→ Links to {rom.linkedName}</span>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                    </React.Fragment>
              ))}
            </div>

            <div className="modal-actions" style={{ marginTop: 16 }}>
              <button className="btn btn-ghost" onClick={() => {
                setRoms([]); setExtraPaths(savedFolders); setRomDirs([]); setRemovedDirs(new Set()); setPhase("emulator");
              }}>← Back</button>
              <button
                className="btn btn-primary"
                disabled={selectedCount === 0}
                onClick={doImport}
              >
                Import {selectedCount > 0 ? `${selectedCount} game${selectedCount !== 1 ? "s" : ""}` : "…"}
              </button>
            </div>
          </>
        )}

        {/* ── importing ────────────────────────────────────────────────────── */}
        {phase === "importing" && (
          <div style={{ textAlign: "center", padding: "40px 0" }}>
            <span className="spinner" style={{ width: 28, height: 28 }} />
            <p style={{ marginTop: 16 }}>
              Importing {progress.done} / {progress.total}…
            </p>
          </div>
        )}

        {/* ── done ─────────────────────────────────────────────────────────── */}
        {phase === "done" && (
          <>
            <div style={{ padding: "24px 0", textAlign: "center" }}>
              <div style={{ fontSize: 36, marginBottom: 8 }}>✓</div>
              <p style={{ fontWeight: 600 }}>
                {progress.total - importErrors.length} of {progress.total} games imported
              </p>
              {importErrors.length > 0 && (
                <p style={{ fontSize: 12, color: "var(--text-muted)" }}>
                  Failed: {importErrors.join(", ")}
                </p>
              )}
            </div>
            <div className="modal-actions">
              <button className="btn btn-primary" onClick={() => { onImported(); onClose(); }}>
                Done
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
