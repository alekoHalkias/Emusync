// "Add console" wizard modal. This is the thin shell: it runs the
// useConsoleImport state machine and renders the step component for the
// current phase. State/logic live in console-import/ (hook + pure helpers);
// each phase's UI is its own presentational component there.
import type { ReactElement } from "react";
import type { Props } from "./console-import/types";
import { useConsoleImport } from "./console-import/useConsoleImport";
import { Stepper } from "./console-import/Stepper";
import { Spinner } from "./console-import/Spinner";
import { ConsoleStep } from "./console-import/ConsoleStep";
import { EmulatorStep } from "./console-import/EmulatorStep";
import { ResultsStep } from "./console-import/ResultsStep";
import { DoneStep } from "./console-import/DoneStep";

export default function ConsoleImport({ onClose, onImported, initialConsole }: Props): ReactElement {
  const vm = useConsoleImport({ onClose, onImported, initialConsole });

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal"
        style={{ width: 640, maxHeight: "85vh", display: "flex", flexDirection: "column" }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <h3 style={{ margin: 0 }}>Add console</h3>
          <button className="btn btn-ghost" onClick={onClose}>✕</button>
        </div>

        {vm.showStepper && <Stepper currentStep={vm.currentStep} />}

        {vm.phase === "console"   && <ConsoleStep vm={vm} />}
        {vm.phase === "detecting" && <Spinner message="Looking for compatible emulators…" />}
        {vm.phase === "emulator"  && <EmulatorStep vm={vm} />}
        {vm.phase === "scanning"  && <Spinner message="Scanning for ROMs and saves…" />}
        {vm.phase === "results"   && <ResultsStep vm={vm} />}
        {vm.phase === "importing" && (
          <Spinner muted={false} message={`Importing ${vm.progress.done} / ${vm.progress.total}…`} />
        )}
        {vm.phase === "done"      && <DoneStep vm={vm} />}
      </div>
    </div>
  );
}
