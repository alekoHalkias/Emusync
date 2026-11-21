import { useState } from "react";
import type { ConsoleImportVM } from "./useConsoleImport";
import { GamepadIcon } from "../icons";

// Download page per suggestion, keyed by its first word ("RetroArch with ...",
// "PCSX2 standalone"). test_emulator_suggestions.py keeps this in sync with
// consoles_data.py (#744). Opened externally by window.ts's open handler.
const SUGGESTION_LINKS: Record<string, string> = {
  RetroArch: "https://www.retroarch.com/?page=platforms",
  mGBA: "https://mgba.io/downloads.html",
  Dolphin: "https://dolphin-emu.org/download/",
  PCSX2: "https://pcsx2.net/downloads",
  RPCS3: "https://rpcs3.net/download",
  Azahar: "https://azahar-emu.org/pages/download/",
  Eden: "https://eden-emu.dev/",
};

type InstallItem = { key: string; label: string; run: () => Promise<string | null> };

// Label + Install rows; one install at a time, error under its row (#744, #745).
function InstallList({ title, items }: { title: string; items: InstallItem[] }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  if (!items.length) return null;
  const run = async (item: InstallItem) => {
    setBusy(item.key);
    setErrors(e => ({ ...e, [item.key]: "" }));
    const err = await item.run();
    setBusy(null);
    if (err) setErrors(e => ({ ...e, [item.key]: err }));
  };
  return (
    <div style={{ textAlign: "left", marginTop: 16 }}>
      <p style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>{title}</p>
      {items.map(item => (
        <div key={item.key} style={{ marginBottom: 6 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
            <span style={{ fontSize: 13 }}>{item.label}</span>
            <button className="btn btn-ghost" disabled={busy !== null} onClick={() => run(item)}>
              {busy === item.key ? <span className="spinner" /> : "Install"}
            </button>
          </div>
          {errors[item.key] && (
            <div style={{ fontSize: 12, color: "var(--color-danger, #e5484d)" }}>{errors[item.key]}</div>
          )}
        </div>
      ))}
    </div>
  );
}

type InstallTargets = ConsoleImportVM["install"];
type InstallProps = {
  install: InstallTargets;
  installCore: (coresDir: string, lib: string) => Promise<string | null>;
  installFlatpak: (flatpakId: string) => Promise<string | null>;
};

// Shared with the game/console emulator picker's "More..." panel (#753).
export function InstallOptions({ install, installCore, installFlatpak }: InstallProps) {
  const { retroarch, cores, standalones = [] } = install;
  const coreItems: InstallItem[] = retroarch.flatMap(ra => cores.map(core => ({
    key: `${ra.coresDir}/${core.lib}`,
    label: `${core.folder}${retroarch.length > 1 ? ` (${ra.label})` : ""}`,
    run: () => installCore(ra.coresDir, core.lib),
  })));
  const flatpakItems: InstallItem[] = standalones.map(s => ({
    key: s.flatpakId, label: s.label, run: () => installFlatpak(s.flatpakId),
  }));
  return (
    <>
      <InstallList title="Install an emulator (Flatpak)" items={flatpakItems} />
      <InstallList title="Install a RetroArch core" items={coreItems} />
    </>
  );
}

// Download links for a console's suggested emulators (#744).
export function SuggestionLinks({ suggestions }: { suggestions: unknown }) {
  // Guard against a malformed value from the API (suggestions is occasionally a
  // string, not a list) so callers never crash on .map / .length.
  const list = Array.isArray(suggestions) ? (suggestions as string[]) : [];
  if (!list.length) return null;
  return (
    <div style={{ fontSize: 12, color: "var(--text-muted)", textAlign: "left", display: "inline-block", marginTop: 4 }}>
      {list.map(s => {
        const url = SUGGESTION_LINKS[s.split(" ")[0]];
        return <div key={s}>• {url ? <a href={url} target="_blank" rel="noreferrer">{s}</a> : s}</div>;
      })}
    </div>
  );
}

export function EmulatorStep({ vm }: { vm: ConsoleImportVM }) {
  const { emulators, consoleLabel, emuSel } = vm;
  // Guard against a malformed value from the API (suggestions is occasionally a
  // string, not a list) so the wizard never crashes on .map / .length.
  const suggestions = Array.isArray(vm.suggestions) ? vm.suggestions : [];
  return (
    <>
      {emulators.length === 0 ? (
        <div style={{ padding: "24px 0", textAlign: "center" }}>
          <div style={{ fontSize: 36, marginBottom: 12 }}><GamepadIcon /></div>
          <p style={{ fontWeight: 600, marginBottom: 8 }}>
            No compatible emulator found
          </p>
          <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: suggestions.length ? 12 : 0 }}>
            Please install a compatible emulator for <strong>{consoleLabel}</strong>.
          </p>
          <SuggestionLinks suggestions={suggestions} />
          <InstallOptions install={vm.install} installCore={vm.installCore} installFlatpak={vm.installFlatpak} />
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
