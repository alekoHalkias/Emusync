import { Fragment, useEffect, useState } from "react";
import { findReplace, groupByDir, replaceUnderscores } from "./helpers";
import type { RomEntry } from "./types";
import type { ConsoleImportVM } from "./useConsoleImport";
import { LocationsBlock } from "./LocationsBlock";
import { CheckIcon, GlobeIcon, SaveIcon, UploadIcon } from "../icons";

type StatusFilter = "all" | "new" | "linked" | "save" | "state";

export function ResultsStep({ vm }: { vm: ConsoleImportVM }) {
  const {
    error, roms, selected,
    names, selectedCount, pushSaves, pushStates, romSource, nameWarnings,
  } = vm;

  // Search + filter are local to this step — they only narrow what's shown and
  // never touch import logic (issue #273).
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  // Find/replace title-cleanup tool (issue #283) — operates on visible titles.
  const [findText, setFindText] = useState("");
  const [replaceText, setReplaceText] = useState("");

  // A rescan delivers a fresh `roms` array — clear the search/filter then.
  useEffect(() => {
    setQuery(""); setStatusFilter("all"); setFindText(""); setReplaceText("");
  }, [roms]);

  const matchesStatus = (r: RomEntry) =>
    statusFilter === "all"    ? true :
    statusFilter === "new"    ? !r.linkedSlug :
    statusFilter === "linked" ? !!r.linkedSlug :
    statusFilter === "save"   ? r.saveExists :
    /* state */                 !!r.stateExists;

  const q = query.trim().toLowerCase();
  const visibleRoms = roms.filter(r =>
    (names[r.romPath] ?? r.name).toLowerCase().includes(q) && matchesStatus(r)
  );
  const visibleGrouped = groupByDir(visibleRoms);
  const visiblePaths = visibleRoms.map(r => r.romPath);
  const ignorableSelected = roms.filter(r => selected.has(r.romPath) && !r.existingLocal);
  const visibleSelectedCount = visibleRoms.filter(r => selected.has(r.romPath)).length;
  const allVisibleSelected = visibleRoms.length > 0 && visibleSelectedCount === visibleRoms.length;

  // Bulk title cleanup (issue #283) — rewrite the editable titles of the
  // currently visible rows. The on-import rename keys off these titles.
  const applyToVisible = (fn: (title: string) => string) => {
    for (const r of visibleRoms) vm.setName(r.romPath, fn(names[r.romPath] ?? r.name));
  };
  const doReplaceUnderscores = () => applyToVisible(replaceUnderscores);
  const doFindReplace = () => { if (findText) applyToVisible(t => findReplace(t, findText, replaceText)); };

  return (
    <>
      {error && <p role="alert" className="error-msg" style={{ marginBottom: 12 }}>{error}</p>}

      <LocationsBlock vm={vm} />

      {/* Search + filter (#273), title cleanup on the visible rows (#283) and bulk select, one wrapping row (#652) */}
      {roms.length > 0 && (
        <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 6, flexWrap: "wrap" }}>
          <input
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Search ROMs…"
            style={{ flex: "1 1 140px", minWidth: 0, fontSize: 13, padding: "4px 8px" }}
          />
          <select
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value as StatusFilter)}
            style={{ fontSize: 12, padding: "4px 6px" }}
          >
            <option value="all">All</option>
            <option value="new">New (not yet imported)</option>
            <option value="linked">Already imported</option>
            <option value="save">Has save</option>
            <option value="state">Has state</option>
          </select>
          <button
            className="btn btn-ghost"
            style={{ fontSize: 12, padding: "2px 10px" }}
            onClick={doReplaceUnderscores}
            title="Replace underscores with spaces in the visible titles"
          >
            Replace _ with space
          </button>
          <input
            type="text"
            value={findText}
            onChange={e => setFindText(e.target.value)}
            placeholder="Find…"
            style={{ width: 120, fontSize: 12, padding: "4px 8px" }}
          />
          <input
            type="text"
            value={replaceText}
            onChange={e => setReplaceText(e.target.value)}
            placeholder="Replace with…"
            style={{ width: 120, fontSize: 12, padding: "4px 8px" }}
          />
          <button
            className="btn btn-ghost"
            style={{ fontSize: 12, padding: "2px 10px" }}
            onClick={doFindReplace}
            disabled={!findText}
            title="Find & replace across the visible titles (case-insensitive)"
          >
            Replace all
          </button>
          <span
            style={{ fontSize: 13, color: "var(--text-muted)", marginLeft: "auto", whiteSpace: "nowrap" }}
            title={vm.ignoredCount > 0 ? `${vm.ignoredCount} ignored file${vm.ignoredCount !== 1 ? "s" : ""} hidden - manage them in the console's settings.` : undefined}
          >
            {visibleSelectedCount} of {visibleRoms.length} selected
            {vm.ignoredCount > 0 && ` (${vm.ignoredCount} ignored)`}
          </span>
          <span style={{ display: "flex", gap: 6 }}>
            <button
              className="btn btn-ghost"
              style={{ fontSize: 12, padding: "2px 10px" }}
              disabled={ignorableSelected.length === 0}
              onClick={() => vm.ignoreRoms(ignorableSelected)}
              title="Hide the selected ROMs from this and future scans (files are not touched)"
            >
              Ignore selected
            </button>
            <button
              className="btn btn-ghost"
              style={{ fontSize: 12, padding: "2px 10px" }}
              disabled={visibleRoms.length === 0}
              onClick={() => vm.toggleAll(visiblePaths)}
            >
              {allVisibleSelected ? "Deselect all" : "Select all"}
            </button>
          </span>
        </div>
      )}

      {/* ROM list */}
      <div style={{ flex: 1, overflowY: "auto", border: "2px solid var(--border)", borderRadius: 6 }}>
        {roms.length === 0 ? (
          <div style={{ padding: 24, textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>
            No ROMs found. Try adding a folder above.
          </div>
        ) : visibleRoms.length === 0 ? (
          <div style={{ padding: 24, textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>
            No ROMs match your search/filter.
          </div>
        ) : Object.entries(visibleGrouped).map(([dir, dirRoms]) => (
              <Fragment key={dir}>
              {dirRoms.map(rom => (
                <div
                  key={rom.romPath}
                  style={{
                    display: "flex", alignItems: "flex-start", gap: 10,
                    padding: "6px 12px", borderBottom: "2px solid var(--border)",
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
                  <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 2 }}>
                    <input
                      type="text"
                      value={names[rom.romPath] ?? rom.name}
                      onChange={(e) => vm.setName(rom.romPath, e.target.value)}
                      onClick={(e) => e.stopPropagation()}
                      style={{ fontSize: 13, fontWeight: 500, width: "100%" }}
                    />
                    <div style={{ fontSize: 11, color: "var(--text-muted)", display: "flex", gap: 8, alignItems: "center" }}>
                      {rom.presence === "network" && (
                        <span title="On the network share" style={{ flexShrink: 0 }}><GlobeIcon /></span>
                      )}
                      {rom.presence === "both" && (
                        <span title="On the share with a local copy already present" style={{ flexShrink: 0 }}><SaveIcon /></span>
                      )}
                      {rom.presence === "local" && (
                        <span title="Only on local disk — will be copied to the share and kept as a local copy" style={{ flexShrink: 0 }}><UploadIcon /></span>
                      )}
                      <span className="truncate" style={{ flex: 1, minWidth: 0 }}>
                        {rom.romPath}
                      </span>
                      {rom.existingLocal && (
                        <span title="Already imported here as a local game — will be copied to the share and switched to network play" style={{ color: "var(--accent, #7c8cf8)", flexShrink: 0 }}>↥ Upload to share</span>
                      )}
                      {rom.saveExists && (
                        <span className="ci-ok" style={{ flexShrink: 0 }}><CheckIcon /> Save</span>
                      )}
                      {rom.statePath && rom.stateExists && (
                        <span className="ci-ok" style={{ flexShrink: 0 }}><CheckIcon /> State</span>
                      )}
                      {!!rom.switchSiblingCount && (
                        <span className="ci-ok" style={{ flexShrink: 0 }} title="Synced as part of this game's folder">
                          {rom.switchSiblingCount} other file(s) in folder
                        </span>
                      )}
                      {rom.linkedSlug && !rom.existingLocal && (
                        <span style={{ color: "var(--accent, #7c8cf8)", flexShrink: 0 }}>→ Links to {rom.linkedName}</span>
                      )}
                    </div>
                  </div>
                  {!rom.existingLocal && (
                    <button
                      className="btn btn-ghost"
                      style={{ fontSize: 11, padding: "1px 8px", flexShrink: 0 }}
                      title="Hide this ROM from future scans (the file is not touched)"
                      onClick={e => { e.stopPropagation(); vm.ignoreRoms([rom]); }}
                    >
                      Ignore
                    </button>
                  )}
                </div>
              ))}
              </Fragment>
        ))}
      </div>

      {nameWarnings.length > 0 && (
        <div style={{
          marginTop: 12, padding: "10px 12px",
          background: "var(--warning-bg, rgba(180,120,0,0.15))",
          border: "1px solid var(--warning-border, rgba(180,120,0,0.5))",
          borderRadius: 6, fontSize: 12,
        }}>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>
            {nameWarnings.length === 1
              ? "This name already exists — importing will create a duplicate:"
              : "These names already exist — importing will create duplicates:"}
          </div>
          <ul style={{ margin: "0 0 8px", paddingLeft: 16 }}>
            {nameWarnings.map(n => <li key={n}>{n}</li>)}
          </ul>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-ghost" style={{ fontSize: 12 }} onClick={vm.dismissNameWarnings}>
              Cancel
            </button>
            <button className="btn btn-primary" style={{ fontSize: 12 }} onClick={vm.forceImport}>
              Import anyway
            </button>
          </div>
        </div>
      )}

      <div className="modal-actions" style={{ marginTop: 8, flexWrap: "wrap", alignItems: "center" }}>
        <button className="btn btn-ghost" onClick={vm.backToEmulator}>← Back</button>
        {romSource === "network" ? (
          <span style={{ flex: 1, fontSize: 12, color: "var(--text-muted)" }} title="Network ROMs aren't copied to other devices — every device reads them from the share.">
            <GlobeIcon /> Read from the share on every device
          </span>
        ) : (
          <span style={{ flex: 1, display: "flex", gap: 12, fontSize: 13, justifyContent: "center", flexWrap: "wrap" }}>
            <label className="ci-check">
              <input type="checkbox" checked={pushSaves} onChange={e => vm.setPushSaves(e.target.checked)} />
              Push saves
            </label>
            <label className="ci-check">
              <input type="checkbox" checked={pushStates} onChange={e => vm.setPushStates(e.target.checked)} />
              Push states
            </label>
          </span>
        )}
        {selectedCount === 0 ? (
          // Nothing selected (e.g. every ROM here is already imported) — offer to
          // move on instead of just sitting disabled. In the bulk-library queue
          // this advances to the next console; standalone "Add console" closes
          // the modal, same as Cancel (#462 follow-up).
          <button className="btn btn-primary" onClick={vm.onClose}>
            Skip →
          </button>
        ) : (
          <button
            className="btn btn-primary"
            disabled={nameWarnings.length > 0}
            onClick={vm.doImport}
          >
            Import {selectedCount} game{selectedCount !== 1 ? "s" : ""}
          </button>
        )}
      </div>
    </>
  );
}
