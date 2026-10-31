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
import { ChevronDownIcon, ChevronRightIcon, CloseIcon, WarningIcon } from "./icons";
import type { ConsoleOption } from "./console-import/types";
import Modal from "./Modal";

const emusync = window.emusync;

type LibraryEntry = { path: string; folderName: string; consoleKey: string | null };
type QueueItem = { path: string; folderName: string; consoleKey: string };
type Phase = "source" | "scanning" | "review" | "queue";

type Props = { onClose: () => void; onImported: () => void };

export default function LibraryImport({ onClose, onImported }: Props): ReactElement {
  const [phase, setPhase] = useState<Phase>("source");
  const [source, setSource] = useState<"local" | "network">("local");
  const [libraryRoot, setLibraryRoot] = useState("");
  const [networkEnabled, setNetworkEnabled] = useState(false);
  const [remotePath, setRemotePath] = useState("");
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

  async function pickRemotePath(): Promise<void> {
    const folder = await emusync.dialog.openFolder();
    if (folder) setRemotePath(folder);
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
    // destination + remote path — the exact config keys the single-console
    // wizard already reads on mount, so nothing new needs to be threaded in.
    const cfg = (await emusync.config.load()) ?? {};
    cfg.import_rom_source = { ...(cfg.import_rom_source ?? {}) };
    cfg.import_local_folder = { ...(cfg.import_local_folder ?? {}) };
    cfg.import_remote_path = { ...(cfg.import_remote_path ?? {}) };
    for (const e of matched) {
      cfg.import_rom_source[e.consoleKey!] = source;
      if (source === "network") {
        const folderLocal = `${localDestRoot.replace(/\/$/, "")}/${e.folderName}`;
        cfg.import_local_folder[e.consoleKey!] = folderLocal;
        if (remotePath) cfg.import_remote_path[e.consoleKey!] = remotePath;
      }
    }
    await emusync.config.save(cfg);

    setQueue(matched.map(e => ({ path: e.path, folderName: e.folderName, consoleKey: e.consoleKey! })));
    setQueueIndex(0);
    setPhase("queue");
  }

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

  const networkReady = !networkEnabled
    || (networkEnabled && remotePath && localDestRoot);

  return (
    <Modal size="wizard" onClose={onClose} style={{ maxHeight: "85vh", display: "flex", flexDirection: "column" }}>
      <div className="modal-header">
        <h3 style={{ margin: 0 }}>Import library</h3>
        <button className="btn btn-ghost" aria-label="Close" onClick={onClose}><CloseIcon /></button>
      </div>

      {error && <p role="alert" className="error-msg" style={{ marginBottom: 12 }}>{error}</p>}

      {phase === "source" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {/* Source type — inline radio group */}
          <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
            <span style={{ fontSize: 13, fontWeight: 500, whiteSpace: "nowrap" }}>Source</span>
            <label className="ci-check">
              <input type="radio" name="libsrc" checked={source === "local"} onChange={() => setSource("local")} />
              Local
            </label>
            <label className="ci-check">
              <input type="radio" name="libsrc" checked={source === "network"} onChange={() => setSource("network")} />
              Network drive
            </label>
          </div>

          {/* Library folder — single line */}
          <div className="input-group" style={{ marginBottom: 0 }}>
            <label>Library folder</label>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <button className="btn btn-ghost btn-sm" onClick={pickLibraryRoot}>Choose…</button>
              <span className="truncate" style={{ flex: 1, fontSize: 12, color: "var(--text-muted)" }}>
                {libraryRoot || "Not set"}
              </span>
            </div>
          </div>

          {/* Network drive — collapsible */}
          {source === "network" && (
            <div>
              <button
                className="ci-toggle"
                type="button"
                onClick={() => setNetworkEnabled(e => !e)}
                style={{ display: "flex", alignItems: "center", gap: 6, background: "none", border: "none", cursor: "pointer", padding: "4px 0", fontSize: 13, fontWeight: 500, color: "var(--text-primary)" }}
              >
                {networkEnabled ? <ChevronDownIcon /> : <ChevronRightIcon />}
                Network drive settings
              </button>
              {networkEnabled && (
                <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8, paddingLeft: 20 }}>
                  <div className="input-group" style={{ marginBottom: 0 }}>
                    <label>Remote path</label>
                    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                      <button className="btn btn-ghost btn-sm" onClick={pickRemotePath}>Choose…</button>
                      <span className="truncate" style={{ flex: 1, fontSize: 12, color: "var(--text-muted)" }}>
                        {remotePath || "Not set"}
                      </span>
                    </div>
                    <p style={{ fontSize: 11, color: "var(--text-muted)", margin: "4px 0 0" }}>
                      Shared network location (e.g. \\NAS\Games). Other devices must use the same path.
                    </p>
                  </div>
                  <div className="input-group" style={{ marginBottom: 0 }}>
                    <label>Local destination</label>
                    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                      <button className="btn btn-ghost btn-sm" onClick={pickLocalDestRoot}>Choose…</button>
                      <span className="truncate" style={{ flex: 1, fontSize: 12, color: "var(--text-muted)" }}>
                        {localDestRoot || "Not set"}
                      </span>
                    </div>
                    <p style={{ fontSize: 11, color: "var(--text-muted)", margin: "4px 0 0" }}>
                      Where games get copied for offline play.
                    </p>
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="modal-actions" style={{ marginTop: 4 }}>
            <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
            <button
              className="btn btn-primary"
              disabled={!libraryRoot || (source === "network" && !networkReady)}
              onClick={scanLibrary}
            >
              Scan library →
            </button>
          </div>
        </div>
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
                style={{ display: "flex", alignItems: "center", gap: 10, padding: "6px 0", borderBottom: "2px solid var(--border)" }}
              >
                <span className="truncate" style={{ flex: 1, fontSize: 13 }}>{e.folderName}</span>
                {!e.consoleKey && <span title="No console match found" style={{ color: "var(--text-muted)" }}><WarningIcon /></span>}
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
    </Modal>
  );
}
