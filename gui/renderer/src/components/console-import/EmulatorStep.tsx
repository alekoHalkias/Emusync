import type { ConsoleImportVM } from "./useConsoleImport";

export function EmulatorStep({ vm }: { vm: ConsoleImportVM }) {
  const { emulators, suggestions, consoleLabel, emuSel } = vm;
  return (
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
                  onChange={() => vm.setEmuSel(emu)}
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
        <button className="btn btn-ghost" onClick={vm.backToConsole}>← Back</button>
        {emulators.length === 0 ? (
          <button className="btn btn-ghost" onClick={vm.onClose}>Close</button>
        ) : (
          <button
            className="btn btn-primary"
            disabled={!emuSel}
            onClick={() => vm.scanRoms(vm.extraPaths)}
          >
            Scan for ROMs →
          </button>
        )}
      </div>
    </>
  );
}
