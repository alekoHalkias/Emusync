import type { ConsoleImportVM } from "./useConsoleImport";

export function ConsoleStep({ vm }: { vm: ConsoleImportVM }) {
  return (
    <>
      <div className="input-group" style={{ marginBottom: 24 }}>
        <label>Select a console</label>
        <select
          value={vm.consoleSel}
          onChange={e => vm.setConsoleSel(e.target.value)}
          style={{ width: "100%" }}
        >
          <option value="">— choose a console —</option>
          {vm.consoles.map(c => (
            <option key={c.key} value={c.key}>{c.label}</option>
          ))}
        </select>
      </div>
      <div className="modal-actions">
        <button className="btn btn-ghost" onClick={vm.onClose}>Cancel</button>
        <button className="btn btn-primary" disabled={!vm.consoleSel} onClick={vm.detectEmulators}>
          Next →
        </button>
      </div>
    </>
  );
}
