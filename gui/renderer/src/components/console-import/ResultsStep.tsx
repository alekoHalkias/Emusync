import { Fragment } from "react";
import type { ConsoleImportVM } from "./useConsoleImport";

export function ResultsStep({ vm }: { vm: ConsoleImportVM }) {
  const {
    error, allRomDirs, extraPaths, removedDirs, roms, grouped, selected,
    names, selectedCount, pushSaves, pushStates, romSource, localRomRoot,
  } = vm;

  return (
    <>
      {error && <p className="error-msg" style={{ marginBottom: 12 }}>{error}</p>}

      {/* ROM source: local folder vs network share (issue #255) */}
      <div style={{ marginBottom: 12, display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
        <span style={{ fontSize: 13, fontWeight: 500 }}>ROM source</span>
        <label className="ci-check">
          <input type="radio" name="romsrc" checked={romSource === "local"} onChange={() => vm.setRomSource("local")} />
          Local folder
        </label>
        <label className="ci-check">
          <input type="radio" name="romsrc" checked={romSource === "network"} onChange={() => vm.setRomSource("network")} />
          Network / shared drive
        </label>
      </div>
      {romSource === "network" && (
        <div style={{ marginBottom: 12, fontSize: 12 }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <span style={{ color: "var(--text-muted)" }}>Local copy destination (for offline play):</span>
            <button className="btn btn-ghost" style={{ fontSize: 12, padding: "2px 10px" }} onClick={vm.pickLocalRomRoot}>
              Choose…
            </button>
          </div>
          <div className="truncate" style={{ color: "var(--text-muted)", marginTop: 4 }}>
            {localRomRoot || "Not set — you can still localize each game later from its settings."}
          </div>
        </div>
      )}

      {/* ROM folder list */}
      <div style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6 }}>
          <span style={{ fontSize: 13, fontWeight: 500 }}>ROM folders</span>
          <button
            className="btn btn-ghost"
            style={{ fontSize: 12, padding: "2px 10px" }}
            onClick={vm.addExtraPath}
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
            <span className="truncate" style={{ flex: 1, color: "var(--text-muted)" }}>
              {p}
              {!extraPaths.includes(p) && !removedDirs.has(p) && (
                <span style={{ fontSize: 11, color: "var(--text-muted)" }}> (detected)</span>
              )}
            </span>
            {!removedDirs.has(p) && (
              <button
                className="btn btn-ghost"
                style={{ fontSize: 11, padding: "1px 6px" }}
                onClick={() => extraPaths.includes(p) ? vm.removeExtraPath(p) : vm.removeRomDir(p)}
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
            onClick={() => vm.toggleAll(roms.map(r => r.romPath))}
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
              <Fragment key={dir}>
              {dirRoms.map(rom => (
                <div
                  key={rom.romPath}
                  style={{
                    display: "flex", alignItems: "flex-start", gap: 10,
                    padding: "10px 12px", borderBottom: "1px solid var(--border)",
                    cursor: "pointer",
                  }}
                  onClick={() => vm.toggleRom(rom.romPath)}
                >
                  <input
                    type="checkbox"
                    checked={selected.has(rom.romPath)}
                    onChange={() => vm.toggleRom(rom.romPath)}
                    onClick={e => e.stopPropagation()}
                    style={{ marginTop: 3, flexShrink: 0 }}
                  />
                  <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 4 }}>
                    <input
                      type="text"
                      value={names[rom.romPath] ?? rom.name}
                      onChange={(e) => vm.setName(rom.romPath, e.target.value)}
                      onClick={(e) => e.stopPropagation()}
                      style={{ fontSize: 13, fontWeight: 500, width: "100%" }}
                    />
                    <div className="truncate" style={{ fontSize: 11, color: "var(--text-muted)" }}>
                      {rom.romPath}
                    </div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)", display: "flex", gap: 8, alignItems: "center" }}>
                      {rom.saveExists && (
                        <span className="ci-ok">✓ Save found</span>
                      )}
                      {rom.statePath && rom.stateExists && (
                        <span className="ci-ok">✓ State found</span>
                      )}
                      {rom.linkedSlug && (
                        <span style={{ color: "var(--accent, #7c8cf8)" }}>→ Links to {rom.linkedName}</span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
              </Fragment>
        ))}
      </div>

      {romSource === "network" ? (
        <div style={{ marginTop: 12, fontSize: 12, color: "var(--text-muted)" }}>
          🌐 Network ROMs aren't copied to other devices — every device reads them from the share.
        </div>
      ) : (
        <div style={{ display: "flex", gap: 16, marginTop: 12, fontSize: 13 }}>
          <label className="ci-check">
            <input type="checkbox" checked={pushSaves} onChange={e => vm.setPushSaves(e.target.checked)} />
            Push saves to other devices
          </label>
          <label className="ci-check">
            <input type="checkbox" checked={pushStates} onChange={e => vm.setPushStates(e.target.checked)} />
            Push states to other devices
          </label>
        </div>
      )}

      <div className="modal-actions" style={{ marginTop: 12 }}>
        <button className="btn btn-ghost" onClick={vm.backToEmulator}>← Back</button>
        <button
          className="btn btn-primary"
          disabled={selectedCount === 0}
          onClick={vm.doImport}
        >
          Import {selectedCount > 0 ? `${selectedCount} game${selectedCount !== 1 ? "s" : ""}` : "…"}
        </button>
      </div>
    </>
  );
}
