// Bulk-library import wizard (#462). Scans a library root's immediate
// subfolders, matches each against a console, lets the user correct any
// mismatch, then hands off — one console at a time — to the *existing*
// single-console wizard (ConsoleImport) via its initialConsole/initialRomDirs
// props. No new scan/import logic lives here; this is purely discovery +
// matching + queueing.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import ConsoleImport from "./ConsoleImport";
import { Spinner } from "./console-import/Spinner";
import type { ConsoleOption } from "./console-import/types";

const emusync = window.emusync;

type LibraryEntry = { path: string; folderName: string; consoleKey: string | null };
type QueueItem = { path: string; folderName: string; consoleKey: string };
type Phase = "source" | "scanning" | "review" | "queue";

type Props = { onClose: () => void; onImported: () => void };

export default function LibraryImport({ onClose, onImported }: Props): ReactElement {
  const [phase, setPhase] = useState<Phase>("source");
  const [source, setSource] = useState<"local" | "network">("local");
  const [libraryRoot, setLibraryRoot] = useState("");
  const [localDestRoot, setLocalDestRoot] = useState("");
  const [error, setError] = useState("");
  const [consoles, setConsoles] = useState<ConsoleOption[]>([]);
  const [entries, setEntries] = useState<LibraryEntry[]>([]);
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [queueIndex, setQueueIndex] = useState(0);

  useEffect(() => { emusync.emulator.consoles().then(setConsoles); }, []);

  async function pickLibraryRoot(): Promise<void> {
    const folder = await emusync.dialog.openFolder();
    if (folder) setLibraryRoot(folder);
  }

  async function pickLocalDestRoot(): Promise<void> {
    const folder = await emusync.dialog.openFolder();
    if (folder) setLocalDestRoot(folder);
  }

  async function scanLibrary(): Promise<void> {
    setPhase("scanning");
    setError("");
    try {
      const result = await emusync.emulator.scanLibrary(libraryRoot);
      if (result.length === 0) setError("No folders found in that library root.");
      setEntries(result);
      setPhase("review");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Scan failed.");
      setPhase("source");
    }
  }

  function setEntryConsole(path: string, consoleKey: string): void {
    setEntries(prev => prev.map(e => e.path === path ? { ...e, consoleKey: consoleKey || null } : e));
  }

  const matched = entries.filter(e => e.consoleKey);

  async function startImport(): Promise<void> {
    if (matched.length === 0) {
      setError("Assign at least one folder to a console before continuing.");
      return;
    }
    // Pre-seed each queued console's ROM source + (for network) local-copy
    // destination — the exact config keys the single-console wizard already
    // reads on mount (see EmulatorStep/ResultsStep's romSource), so nothing
    // new needs to be threaded into it for this to work.
    const cfg = (await emusync.config.load()) ?? {};
    cfg.import_rom_source = { ...(cfg.import_rom_source ?? {}) };
    cfg.import_local_folder = { ...(cfg.import_local_folder ?? {}) };
    for (const e of matched) {
      cfg.import_rom_source[e.consoleKey!] = source;
      if (source === "network") {
        cfg.import_local_folder[e.consoleKey!] = `${localDestRoot.replace(/\/$/, "")}/${e.folderName}`;
      }
    }
    await emusync.config.save(cfg);

    setQueue(matched.map(e => ({ path: e.path, folderName: e.folderName, consoleKey: e.consoleKey! })));
    setQueueIndex(0);
    setPhase("queue");
  }

  // ponytail: no dedicated "cancel remaining" control — closing/cancelling a
  // per-console step just advances to the next queued console (same signal
  // as "done with this one"). Add a real abort-batch button if long queues
  // make that annoying in practice.
  function advanceQueue(): void {
    if (queueIndex + 1 < queue.length) setQueueIndex(i => i + 1);
    else onClose();
  }

  if (phase === "queue" && queue.length > 0) {
    const item = queue[queueIndex];
    const label = consoles.find(c => c.key === item.consoleKey)?.label ?? item.consoleKey;
    return (
      <ConsoleImport
        key={queueIndex}
        initialConsole={item.consoleKey}
        initialRomDirs={[item.path]}
        title={`Import library — ${label} (${queueIndex + 1} of ${queue.length})`}
        onClose={advanceQueue}
        onImported={onImported}
      />
    );
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal"
        style={{ width: "clamp(640px, 70vw, 960px)", maxHeight: "85vh", display: "flex", flexDirection: "column" }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <h3 style={{ margin: 0 }}>Import library</h3>
          <button className="btn btn-ghost" onClick={onClose}>✕</button>
        </div>

        {error && <p className="error-msg" style={{ marginBottom: 12 }}>{error}</p>}

        {phase === "source" && (
          <>
            <div style={{ marginBottom: 16, display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
              <span style={{ fontSize: 13, fontWeight: 500 }}>Library location</span>
              <label className="ci-check">
                <input type="radio" name="libsrc" checked={source === "local"} onChange={() => setSource("local")} />
                Local folder
              </label>
              <label className="ci-check">
                <input type="radio" name="libsrc" checked={source === "network"} onChange={() => setSource("network")} />
                Network / shared drive
              </label>
            </div>

            <div className="input-group" style={{ marginBottom: 16 }}>
              <label>
                {source === "network" ? "Network library folder" : "Library folder"} — contains one subfolder per console
              </label>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <button className="btn btn-ghost" onClick={pickLibraryRoot}>Choose…</button>
                <span className="truncate" style={{ color: "var(--text-muted)", fontSize: 12 }}>
                  {libraryRoot || "Not set"}
                </span>
              </div>
            </div>

            {source === "network" && (
              <div className="input-group" style={{ marginBottom: 16 }}>
                <label>Local destination — where games get copied for offline play</label>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <button className="btn btn-ghost" onClick={pickLocalDestRoot}>Choose…</button>
                  <span className="truncate" style={{ color: "var(--text-muted)", fontSize: 12 }}>
                    {localDestRoot || "Not set"}
                  </span>
                </div>
              </div>
            )}

            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
              <button
                className="btn btn-primary"
                disabled={!libraryRoot || (source === "network" && !localDestRoot)}
                onClick={scanLibrary}
              >
                Scan library →
              </button>
            </div>
          </>
        )}

        {phase === "scanning" && <Spinner message="Scanning library folders…" />}

        {phase === "review" && (
          <>
            <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 12 }}>
              {entries.length} folder{entries.length !== 1 ? "s" : ""} found. Confirm or correct each console match —
              folders left unassigned are skipped.
            </p>
            <div style={{ flex: 1, overflowY: "auto", marginBottom: 12 }}>
              {entries.map(e => (
                <div
                  key={e.path}
                  style={{ display: "flex", alignItems: "center", gap: 10, padding: "6px 0", borderBottom: "1px solid var(--border)" }}
                >
                  <span className="truncate" style={{ flex: 1, fontSize: 13 }}>{e.folderName}</span>
                  {!e.consoleKey && <span title="No console match found" style={{ color: "var(--text-muted)" }}>⚠</span>}
                  <select
                    value={e.consoleKey ?? ""}
                    onChange={ev => setEntryConsole(e.path, ev.target.value)}
                    style={{ minWidth: 220 }}
                  >
                    <option value="">— skip this folder —</option>
                    {consoles.map(c => <option key={c.key} value={c.key}>{c.label}</option>)}
                  </select>
                </div>
              ))}
            </div>
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setPhase("source")}>← Back</button>
              <button className="btn btn-primary" onClick={startImport}>
                Import {matched.length} console{matched.length !== 1 ? "s" : ""} →
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
