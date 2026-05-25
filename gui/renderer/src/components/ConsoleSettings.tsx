import React, { useEffect, useState } from "react";

type ConsoleInfo = {
  key: string;
  longName: string;
  abbreviation: string;
  emulator: string | null;
  emulatorPath: string | null;
  romFolder: string | null;
  saveFolder: string | null;
  stateFolder: string | null;
};

type DetectedEmulator = {
  id: string;
  label: string;
  saveDir: string;
  stateDir?: string;
};

type Props = {
  onClose: () => void;
};

const CONSOLE_ABBREV: Record<string, string> = {
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

export default function ConsoleSettings({ onClose }: Props): React.ReactElement {
  const [consoles, setConsoles] = useState<ConsoleInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [detectingConsole, setDetectingConsole] = useState<string | null>(null);
  const [emulatorsByConsole, setEmulatorsByConsole] = useState<Record<string, DetectedEmulator[]>>({});
  const [selectedEmulators, setSelectedEmulators] = useState<Record<string, string>>({});
  const [editingPaths, setEditingPaths] = useState<Record<string, boolean>>({});
  const [pathValues, setPathValues] = useState<Record<string, { rom?: string; save?: string; state?: string }>>({});

  useEffect(() => {
    async function loadConsoles(): Promise<void> {
      try {
        const consoleDefs = await (window as any).emusync.emulator.consoles();
        const infos: ConsoleInfo[] = consoleDefs.map((c: any) => ({
          key: c.key,
          longName: c.label,
          abbreviation: CONSOLE_ABBREV[c.key] || c.key.toUpperCase(),
          emulator: null,
          emulatorPath: null,
          romFolder: null,
          saveFolder: null,
          stateFolder: null,
        }));
        setConsoles(infos);
        setLoading(false);
      } catch (e) {
        console.error("Failed to load consoles:", e);
        setLoading(false);
      }
    }
    loadConsoles();
  }, []);

  async function detectConsoleEmulators(consoleKey: string): Promise<void> {
    setDetectingConsole(consoleKey);
    try {
      const result = await (window as any).emusync.emulator.detect(consoleKey);
      const emus: DetectedEmulator[] = result.options.map((o: any) => ({
        id: o.id,
        label: o.label,
        saveDir: o.saveDir,
        stateDir: o.stateDir,
      }));
      setEmulatorsByConsole(prev => ({ ...prev, [consoleKey]: emus }));
      if (emus.length > 0) {
        setSelectedEmulators(prev => ({
          ...prev,
          [consoleKey]: emus[0].id,
        }));
        const emu = emus[0];
        setPathValues(prev => ({
          ...prev,
          [consoleKey]: {
            save: emu.saveDir,
            state: emu.stateDir,
          },
        }));
      }
    } catch (e) {
      console.error(`Failed to detect emulators for ${consoleKey}:`, e);
    } finally {
      setDetectingConsole(null);
    }
  }

  function togglePathEditing(consoleKey: string): void {
    setEditingPaths(prev => ({
      ...prev,
      [consoleKey]: !prev[consoleKey],
    }));
  }

  function updatePath(consoleKey: string, pathType: 'rom' | 'save' | 'state', value: string): void {
    setPathValues(prev => ({
      ...prev,
      [consoleKey]: {
        ...prev[consoleKey],
        [pathType]: value,
      },
    }));
  }

  async function selectFolder(consoleKey: string, pathType: 'rom' | 'save' | 'state'): Promise<void> {
    const folder = await (window as any).emusync.dialog.openFolder();
    if (folder) {
      updatePath(consoleKey, pathType, folder);
    }
  }

  return (
    <div style={{ padding: "20px", maxWidth: "1400px", margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24 }}>
        <h2 style={{ margin: 0 }}>Console Settings</h2>
        <button className="btn btn-ghost" onClick={onClose}>✕</button>
      </div>

      {loading ? (
        <div style={{ textAlign: "center", padding: "40px 0" }}>
          <span className="spinner" style={{ width: 24, height: 24 }} />
        </div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: "2px solid var(--border)" }}>
                <th style={{ padding: "12px 8px", textAlign: "left", fontWeight: 600, minWidth: 160 }}>Console</th>
                <th style={{ padding: "12px 8px", textAlign: "left", fontWeight: 600, minWidth: 140 }}>Emulator</th>
                <th style={{ padding: "12px 8px", textAlign: "left", fontWeight: 600, minWidth: 200 }}>ROM Folder</th>
                <th style={{ padding: "12px 8px", textAlign: "left", fontWeight: 600, minWidth: 200 }}>Save Folder</th>
                <th style={{ padding: "12px 8px", textAlign: "left", fontWeight: 600, minWidth: 200 }}>State Folder</th>
                <th style={{ padding: "12px 8px", textAlign: "left", fontWeight: 600, minWidth: 80 }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {consoles.map((console, idx) => {
                const emus = emulatorsByConsole[console.key] || [];
                const selectedEmuId = selectedEmulators[console.key];
                const selectedEmu = emus.find(e => e.id === selectedEmuId);
                const isEditing = editingPaths[console.key];
                const paths = pathValues[console.key] || {};

                return (
                  <tr key={console.key} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td style={{ padding: "12px 8px", verticalAlign: "top" }}>
                      <div style={{ fontWeight: 500 }}>{console.longName}</div>
                      <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{console.abbreviation}</div>
                    </td>
                    <td style={{ padding: "12px 8px", verticalAlign: "top" }}>
                      {detectingConsole === console.key ? (
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <span className="spinner" style={{ width: 12, height: 12 }} />
                          <span style={{ fontSize: 11 }}>Detecting…</span>
                        </div>
                      ) : emus.length === 0 ? (
                        <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                          No emulator detected
                          <button
                            className="btn btn-ghost"
                            style={{ fontSize: 11, padding: "2px 8px", marginLeft: 8 }}
                            onClick={() => detectConsoleEmulators(console.key)}
                          >
                            Detect
                          </button>
                        </div>
                      ) : (
                        <>
                          <select
                            value={selectedEmuId || ""}
                            onChange={(e) => {
                              const newEmuId = e.target.value;
                              setSelectedEmulators(prev => ({ ...prev, [console.key]: newEmuId }));
                              const emu = emus.find(em => em.id === newEmuId);
                              if (emu) {
                                setPathValues(prev => ({
                                  ...prev,
                                  [console.key]: {
                                    save: emu.saveDir,
                                    state: emu.stateDir,
                                  },
                                }));
                              }
                            }}
                            style={{ fontSize: 13, padding: "4px", width: "100%", maxWidth: 180 }}
                          >
                            {emus.map(emu => (
                              <option key={emu.id} value={emu.id}>{emu.label}</option>
                            ))}
                          </select>
                          <button
                            className="btn btn-ghost"
                            style={{ fontSize: 11, padding: "2px 8px", marginTop: 4 }}
                            onClick={() => detectConsoleEmulators(console.key)}
                          >
                            Re-detect
                          </button>
                        </>
                      )}
                    </td>
                    <td style={{ padding: "12px 8px", verticalAlign: "top" }}>
                      {isEditing ? (
                        <div style={{ display: "flex", gap: 4 }}>
                          <input
                            type="text"
                            value={paths.rom || ""}
                            onChange={(e) => updatePath(console.key, 'rom', e.target.value)}
                            placeholder="/path/to/roms"
                            style={{ fontSize: 12, padding: "4px 6px", flex: 1, minWidth: 0 }}
                          />
                          <button
                            className="btn btn-ghost"
                            style={{ fontSize: 11, padding: "2px 6px" }}
                            onClick={() => selectFolder(console.key, 'rom')}
                          >
                            📁
                          </button>
                        </div>
                      ) : (
                        <div style={{ fontSize: 12, color: paths.rom ? "inherit" : "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {paths.rom || "—"}
                        </div>
                      )}
                    </td>
                    <td style={{ padding: "12px 8px", verticalAlign: "top" }}>
                      {isEditing ? (
                        <div style={{ display: "flex", gap: 4 }}>
                          <input
                            type="text"
                            value={paths.save || ""}
                            onChange={(e) => updatePath(console.key, 'save', e.target.value)}
                            placeholder="/path/to/saves"
                            style={{ fontSize: 12, padding: "4px 6px", flex: 1, minWidth: 0 }}
                          />
                          <button
                            className="btn btn-ghost"
                            style={{ fontSize: 11, padding: "2px 6px" }}
                            onClick={() => selectFolder(console.key, 'save')}
                          >
                            📁
                          </button>
                        </div>
                      ) : (
                        <div style={{ fontSize: 12, color: paths.save ? "inherit" : "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {paths.save || selectedEmu?.saveDir || "—"}
                        </div>
                      )}
                    </td>
                    <td style={{ padding: "12px 8px", verticalAlign: "top" }}>
                      {isEditing ? (
                        <div style={{ display: "flex", gap: 4 }}>
                          <input
                            type="text"
                            value={paths.state || ""}
                            onChange={(e) => updatePath(console.key, 'state', e.target.value)}
                            placeholder="/path/to/states"
                            style={{ fontSize: 12, padding: "4px 6px", flex: 1, minWidth: 0 }}
                          />
                          <button
                            className="btn btn-ghost"
                            style={{ fontSize: 11, padding: "2px 6px" }}
                            onClick={() => selectFolder(console.key, 'state')}
                          >
                            📁
                          </button>
                        </div>
                      ) : (
                        <div style={{ fontSize: 12, color: paths.state ? "inherit" : "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {paths.state || selectedEmu?.stateDir || "—"}
                        </div>
                      )}
                    </td>
                    <td style={{ padding: "12px 8px", verticalAlign: "top" }}>
                      <button
                        className="btn btn-ghost"
                        style={{ fontSize: 11, padding: "4px 8px" }}
                        onClick={() => togglePathEditing(console.key)}
                      >
                        {isEditing ? "✓ Done" : "✎ Edit"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
