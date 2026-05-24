import React, { useEffect, useState } from "react";
import { addGame, setGameDevice, listGames } from "../api";

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

export default function ConsoleImport({ onClose, onImported }: Props): React.ReactElement {
  const [phase, setPhase]         = useState<Phase>("console");
  const [consoles, setConsoles]   = useState<ConsoleOption[]>([]);
  const [consoleSel, setConsoleSel] = useState("");
  const [emulators, setEmulators] = useState<EmulatorOption[]>([]);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [emuSel, setEmuSel]       = useState<EmulatorOption | null>(null);
  const [extraPaths, setExtraPaths] = useState<string[]>([]);
  const [romDirs, setRomDirs]     = useState<string[]>([]);
  const [roms, setRoms]           = useState<RomEntry[]>([]);
  const [selected, setSelected]   = useState<Set<string>>(new Set());
  const [names, setNames]         = useState<Record<string, string>>({});
  const [error, setError]         = useState("");
  const [progress, setProgress]   = useState({ done: 0, total: 0 });
  const [importErrors, setImportErrors] = useState<string[]>([]);

  useEffect(() => {
    (window as any).emusync.emulator.consoles().then(setConsoles);
  }, []);

  async function detectEmulators(): Promise<void> {
    setPhase("detecting");
    try {
      const { options, suggestions: sugg } =
        await (window as any).emusync.emulator.detect(consoleSel);
      setEmulators(options);
      setSuggestions(sugg);
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
      const existingGames = await listGames();

      // Extract ROM filename from path (without extension)
      const getRomFileName = (path: string): string => {
        const filename = path.split("/").pop() || "";
        return filename.replace(/\.[^.]+$/, "").toLowerCase();
      };

      const romsWithMatches = result.roms
        .map((rom: RomEntry) => {
          const romFileName = getRomFileName(rom.romPath);
          const nameLower = rom.name.toLowerCase();

          // Match if either game name or ROM filename matches an existing game
          const match = existingGames.find((g: any) => {
            const existingName = g.name.toLowerCase();
            return existingName === nameLower || existingName === romFileName;
          });

          return {
            ...rom,
            romFileName,
            existingGameSlug: match?.slug,
          };
        })
        // Filter out games that are already imported (have a match)
        .filter((rom: RomEntry) => !rom.existingGameSlug);

      setRoms(romsWithMatches);
      setRomDirs(result.romDirs ?? []);
      setSelected(new Set(romsWithMatches.map((r: RomEntry) => r.romPath)));
      setPhase("results");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Scan failed.");
      setPhase("results");
    }
  }

  async function addExtraPath(): Promise<void> {
    const folder = await (window as any).emusync.dialog.openFolder();
    if (!folder) return;
    const updated = [...extraPaths, folder];
    setExtraPaths(updated);
    scanRoms(updated);
  }

  function removeExtraPath(path: string): void {
    const updated = extraPaths.filter(p => p !== path);
    setExtraPaths(updated);
    scanRoms(updated);
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
    for (let i = 0; i < toImport.length; i++) {
      const rom = toImport[i];
      try {
        const displayName = names[rom.romPath] ?? rom.name;
        const game = await addGame(displayName);
        await setGameDevice(game.slug, {
          rom_path: rom.romPath,
          save_path: rom.savePath,
          launch_command: rom.launchCommand,
          state_path: rom.stateExists ? (rom.statePath ?? "") : "",
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
  const allRomDirs = [...new Set([...romDirs, ...extraPaths])];

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
                setEmulators([]); setEmuSel(null); setSuggestions([]); setPhase("console");
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
                    textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p}</span>
                  {extraPaths.includes(p) && (
                    <button
                      className="btn btn-ghost"
                      style={{ fontSize: 11, padding: "1px 6px" }}
                      onClick={() => removeExtraPath(p)}
                    >✕</button>
                  )}
                </div>
              ))}
            </div>

            {/* ROM list */}
            <div style={{ flex: 1, overflowY: "auto", border: "1px solid var(--border)", borderRadius: 6 }}>
              {roms.length === 0 ? (
                <div style={{ padding: 24, textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>
                  No ROMs found. Try adding a folder above.
                </div>
              ) : Object.entries(grouped).map(([dir, dirRoms]) => {
                const allPaths = dirRoms.map(r => r.romPath);
                const allSel   = allPaths.every(p => selected.has(p));
                return (
                  <div key={dir}>
                    <div style={{
                      display: "flex", alignItems: "center", gap: 8,
                      padding: "6px 12px", background: "var(--bg-secondary)",
                      borderBottom: "1px solid var(--border)",
                      fontSize: 11, color: "var(--text-muted)", position: "sticky", top: 0,
                    }}>
                      <input type="checkbox" checked={allSel} onChange={() => toggleAll(allPaths)} />
                      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {dir}
                      </span>
                    </div>
                    {dirRoms.map(rom => (
                      <div
                        key={rom.romPath}
                        style={{
                          display: "flex", alignItems: "center", gap: 10,
                          padding: "7px 12px", borderBottom: "1px solid var(--border)",
                          cursor: "pointer",
                        }}
                        onClick={() => toggleRom(rom.romPath)}
                      >
                        <input
                          type="checkbox"
                          checked={selected.has(rom.romPath)}
                          onChange={() => toggleRom(rom.romPath)}
                          onClick={e => e.stopPropagation()}
                        />
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <input
                            type="text"
                            value={names[rom.romPath] ?? rom.name}
                            onChange={(e) => setNames({ ...names, [rom.romPath]: e.target.value })}
                            onClick={(e) => e.stopPropagation()}
                            style={{ fontSize: 13, fontWeight: 500, width: "100%", marginBottom: 4 }}
                          />
                          <div style={{ fontSize: 11, color: "var(--text-muted)",
                            marginTop: 1, display: "flex", gap: 8, flexWrap: "wrap" }}>
                            {rom.saveExists && (
                              <span style={{ color: "var(--green, #4caf50)" }}>✓ Save found</span>
                            )}
                            {rom.statePath && rom.stateExists && (
                              <span style={{ color: "var(--green, #4caf50)" }}>✓ State found</span>
                            )}
                            {(rom.consoleName || rom.coreName) && (
                              <span style={{ opacity: 0.7 }}>
                                {[rom.consoleName, rom.coreName].filter(Boolean).join(" · ")}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>

            <div className="modal-actions" style={{ marginTop: 16 }}>
              <button className="btn btn-ghost" onClick={() => {
                setRoms([]); setExtraPaths([]); setRomDirs([]); setPhase("emulator");
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
