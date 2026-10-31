// Locations for the console import results step (#644): the local folder, the
// optional network folder with its share-match chip, and the scanned-folder list.
import { useState } from "react";
import type { ConsoleImportVM } from "./useConsoleImport";
import { CloseIcon } from "../icons";

const btn = { fontSize: 12, padding: "2px 10px" } as const;

function Row({ label, path, empty, onPick, onClear, children }: {
  label: string; path: string; empty: string; onPick: () => void; onClear: () => void; children?: React.ReactNode;
}) {
  return (
    <div style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12, marginBottom: 4 }}>
      <span style={{ width: 110, fontWeight: 500, fontSize: 13, flexShrink: 0 }}>{label}</span>
      <button className="btn btn-ghost" style={btn} onClick={onPick}>Choose…</button>
      <span className="truncate" style={{ flex: 1, color: "var(--text-muted)" }} title={path}>{path || empty}</span>
      {children}
      {path && (
        <button className="btn btn-ghost" style={{ fontSize: 11, padding: "1px 6px" }} onClick={onClear}
          title="Clear" aria-label={`Clear ${label.toLowerCase()}`}><CloseIcon /></button>
      )}
    </div>
  );
}

export function LocationsBlock({ vm }: { vm: ConsoleImportVM }) {
  const { networkRoot, localRomRoot, share, linkedCount, allRomDirs, extraPaths, removedDirs } = vm;
  const [showFolders, setShowFolders] = useState(false);

  const chip: { text: string; color: string } | null =
    share.status === "checking"   ? { text: "Checking share…", color: "var(--text-muted)" } :
    share.status === "same"       ? { text: `Same share as ${share.peer?.device_name}`, color: "var(--accent, #7c8cf8)" } :
    share.status === "different"  ? { text: `Different share than ${share.peer?.device_name}`, color: "var(--color-danger, #e5484d)" } :
    share.status === "new"        ? { text: "Share registered", color: "var(--text-muted)" } :
    share.status === "unverified" ? { text: "Unverified", color: "var(--text-muted)" } : null;

  return (
    <div style={{ marginBottom: 12 }}>
      <Row label="Local folder" path={localRomRoot} empty="Not set" onPick={vm.pickLocalRomRoot} onClear={vm.clearLocalRoot} />
      <Row label="Network folder" path={networkRoot} empty="Not set (optional)" onPick={vm.pickNetworkRoot} onClear={vm.clearNetworkRoot}>
        {chip && (
          <span style={{ fontSize: 11, color: chip.color, whiteSpace: "nowrap" }}
            title={share.status === "unverified" ? "Could not read or write .emusync-share-id in this folder, so it cannot be matched with other devices" : undefined}>
            {chip.text}
          </span>
        )}
      </Row>
      {linkedCount ? (
        <div style={{ fontSize: 12, color: "var(--text-muted)", margin: "2px 0 4px" }}>
          {linkedCount} game{linkedCount !== 1 ? "s" : ""} linked from {share.peer?.device_name ?? "another device"}
        </div>
      ) : null}

      <button type="button" className="btn btn-ghost" style={{ ...btn, marginTop: 2 }} onClick={() => setShowFolders(v => !v)}>
        {showFolders ? "▾" : "▸"} {allRomDirs.length} folder{allRomDirs.length !== 1 ? "s" : ""} scanned
      </button>
      {showFolders && (
        <div style={{ marginTop: 6 }}>
          {allRomDirs.length === 0 && (
            <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "0 0 4px" }}>
              No ROM folder detected — add one below.
            </p>
          )}
          {allRomDirs.map(p => (
            <div key={p} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, marginBottom: 4 }}>
              <span className="truncate" style={{ flex: 1, color: "var(--text-muted)" }}>
                {p}
                {!extraPaths.includes(p) && !removedDirs.has(p) && (
                  <span style={{ fontSize: 11 }}> (detected)</span>
                )}
              </span>
              <button
                className="btn btn-ghost"
                style={{ fontSize: 11, padding: "1px 6px" }}
                onClick={() => extraPaths.includes(p) ? vm.removeExtraPath(p) : vm.removeRomDir(p)}
                title={extraPaths.includes(p) ? "Remove folder" : "Ignore this folder"}
                aria-label={extraPaths.includes(p) ? "Remove folder" : "Ignore this folder"}
              ><CloseIcon /></button>
            </div>
          ))}
          <button className="btn btn-ghost" style={btn} onClick={vm.addExtraPath}>+ Add folder</button>
        </div>
      )}
    </div>
  );
}
