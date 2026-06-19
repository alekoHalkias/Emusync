import { Fragment } from "react";
import { STEP_LABELS } from "./helpers";

export function Stepper({ currentStep }: { currentStep: number }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 20, fontSize: 12 }}>
      {STEP_LABELS.map((label, i) => {
        const active = i === currentStep;
        const done   = i < currentStep;
        return (
          <Fragment key={label}>
            {i > 0 && <span style={{ color: "var(--text-muted)" }}>›</span>}
            <span style={{
              color: active ? "var(--accent, #7c8cf8)" : done ? "var(--green, #4caf50)" : "var(--text-muted)",
              fontWeight: active ? 600 : 400,
            }}>
              {done ? `✓ ${label}` : label}
            </span>
          </Fragment>
        );
      })}
    </div>
  );
}
