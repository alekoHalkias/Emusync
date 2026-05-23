import React, { useCallback, useEffect, useState } from "react";
import { addGame, setGameDevice } from "../api";

type RomEntry = {
  name: string;
  romPath: string;
  savePath: string;
  saveExists: boolean;
  launchCommand: string;
  consoleName?: string;   // e.g. "Game Boy Advance"
  coreName?: string;      // e.g. "mGBA"
};

type ScanResult = {
  emulators: { type: string; label: string }[];
  romDirs: string[];
  roms: RomEntry[];
};

type Props = {
  onClose: () => void;
  onImported: () => void;
};

export default function EmulatorImport({ onClose, onImported }: Props): React.ReactElement {
  const [phase, setPhase] = useState<"scanning" | "results" | "importing" | "done">("scanning");
  const [extraPaths, setExtraPaths] = useState<string[]>([]);
  const [result, setResult] = useState<ScanResult | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState("");
  const [importProgress, setImportProgress] = useState({ done: 0, total: 0 });
  const [importErrors, setImportErrors] = useState<string[]>([]);

  const runScan = useCallback(async (paths: string[]) => {
    setPhase("scanning");
    setError("");
    try {
      const r = await (window as any).emusync.emulator.scan(paths);
      setResult(r);
      // Default: select all ROMs
      setSelected(new Set(r.roms.map((rom: RomEntry) => rom.romPath)));
      setPhase("results");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Scan failed.");
      setPhase("results");
    }
  }, []);

  // Auto-scan on mount
  useEffect(() => { runScan([]); }, [runScan]);

  async function addExtraPath(): Promise<void> {
    const folder = await (window as any).emusync.dialog.openFolder();
    if (!folder) return;
    const updated = [...extraPaths, folder];
    setExtraPaths(updated);
    runScan(updated);
  }

  function removeExtraPath(path: string): void {
    const updated = extraPaths.filter(p => p !== path);
    setExtraPaths(updated);
    runScan(updated);
  }

  function toggleRom(romPath: string): void {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(romPath) ? next.delete(romPath) : next.add(romPath);
      return next;
    });
  }

  function toggleAll(allPaths: string[]): void {
    if (allPaths.every(p => selected.has(p))) {
      setSelected(prev => {
        const next = new Set(prev);
        allPaths.forEach(p => next.delete(p));
        return next;
      });
    } else {
      setSelected(prev => new Set([...prev, ...allPaths]));
    }
  }

  async function doImport(): Promise<void> {
    if (!result) return;
    const toImport = result.roms.filter(r => selected.has(r.romPath));
    setImportProgress({ done: 0, total: toImport.length });
    setImportErrors([]);
    setPhase("importing");

    const errs: string[] = [];
    for (let i = 0; i < toImport.length; i++) {
      const rom = toImport[i];
      try {
        const game = await addGame(rom.name);
        await setGameDevice(game.slug, {
          rom_path: rom.romPath,
          save_path: rom.savePath,
          launch_command: rom.launchCommand,
        });
      } catch {
        errs.push(rom.name);
      }
      setImportProgress({ done: i + 1, total: toImport.length });
    }

    setImportErrors(errs);
    setPhase("done");
  }

  // ── Group ROMs by parent directory ──────────────────────────────────────────
  const grouped: Record<string, RomEntry[]> = {};
  if (result) {
    for (const rom of result.roms) {
      const dir = rom.romPath.replace(/[^/]+$/, "").replace(/\/$/, "") || "/";
      (grouped[dir] = grouped[dir] ?? []).push(rom);
    }
  }

  const selectedCount = result ? result.roms.filter(r => selected.has(r.romPath)).length : 0;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal"
        style={{ width: 620, maxHeight: "80vh", display: "flex", flexDirection: "column" }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <h3 style={{ margin: 0 }}>Import from emulator</h3>
          <button className="btn btn-ghost" onClick={onClose}>✕</button>
        </div>

        {/* ── Scanning ─────────────────────────────────────────────────────── */}
        {phase === "scanning" && (
          <div style={{ textAlign: "center", padding: "40px 0" }}>
            <span className="spinner" style={{ width: 28, height: 28 }} />
            <p style={{ marginTop: 16, color: "var(--text-muted)" }}>Scanning for emulators and ROMs…</p>
          </div>
        )}

        {/* ── Results ──────────────────────────────────────────────────────── */}
        {phase === "results" && (
          <>
            {error && <p className="error-msg" style={{ marginBottom: 12 }}>{error}</p>}

            {/* Detected emulators */}
            <div style={{ marginBottom: 12 }}>
              {result?.emulators.length ? (
                result.emulators.map(e => (
                  <div key={e.label} style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 2 }}>
                    ✓ Found: <strong>{e.label}</strong>
                  </div>
                ))
              ) : (
                <p style={{ fontSize: 13, color: "var(--text-muted)", margin: 0 }}>
                  No emulators detected automatically — add a ROM folder below.
                </p>
              )}
            </div>

            {/* Extra paths */}
            <div style={{ marginBottom: 12 }}>
              <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontSize: 13, fontWeight: 500 }}>ROM folders</span>
                <button className="btn btn-ghost" style={{ fontSize: 12, padding: "2px 10px" }} onClick={addExtraPath}>
                  + Add folder
                </button>
              </div>
              {extraPaths.map(p => (
                <div key={p} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, marginBottom: 4 }}>
                  <span style={{ flex: 1, color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p}</span>
                  <button className="btn btn-ghost" style={{ fontSize: 11, padding: "1px 6px" }} onClick={() => removeExtraPath(p)}>✕</button>
                </div>
              ))}
            </div>

            {/* ROM list */}
            <div style={{ flex: 1, overflowY: "auto", border: "1px solid var(--border)", borderRadius: 6 }}>
              {!result || result.roms.length === 0 ? (
                <div style={{ padding: 24, textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>
                  No ROMs found. Try adding a folder above.
                </div>
              ) : (
                Object.entries(grouped).map(([dir, roms]) => {
                  const allPaths = roms.map(r => r.romPath);
                  const allSelected = allPaths.every(p => selected.has(p));
                  return (
                    <div key={dir}>
                      {/* Directory header */}
                      <div
                        style={{
                          display: "flex", alignItems: "center", gap: 8,
                          padding: "6px 12px", background: "var(--bg-secondary)",
                          borderBottom: "1px solid var(--border)", fontSize: 11,
                          color: "var(--text-muted)", position: "sticky", top: 0,
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={allSelected}
                          onChange={() => toggleAll(allPaths)}
                        />
                        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{dir}</span>
                      </div>
                      {/* ROM rows */}
                      {roms.map(rom => (
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
                            <div style={{ fontSize: 13, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                              {rom.name}
                            </div>
                            <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 1, display: "flex", gap: 8, flexWrap: "wrap" }}>
                              {rom.saveExists
                                ? <span style={{ color: "var(--green, #4caf50)" }}>✓ Save matched</span>
                                : <span>Save: {rom.savePath.replace(/.*\//, "")}</span>
                              }
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
                })
              )}
            </div>

            {/* Footer */}
            <div className="modal-actions" style={{ marginTop: 16 }}>
              <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
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

        {/* ── Importing ────────────────────────────────────────────────────── */}
        {phase === "importing" && (
          <div style={{ textAlign: "center", padding: "40px 0" }}>
            <span className="spinner" style={{ width: 28, height: 28 }} />
            <p style={{ marginTop: 16 }}>
              Importing {importProgress.done} / {importProgress.total}…
            </p>
          </div>
        )}

        {/* ── Done ─────────────────────────────────────────────────────────── */}
        {phase === "done" && (
          <>
            <div style={{ padding: "24px 0", textAlign: "center" }}>
              <div style={{ fontSize: 32, marginBottom: 8 }}>✓</div>
              <p style={{ fontWeight: 600 }}>
                {importProgress.total - importErrors.length} of {importProgress.total} games imported
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
