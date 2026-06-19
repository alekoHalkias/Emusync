import type { ReactNode } from "react";

/** Centered spinner + message — the detecting / scanning / importing screens. */
export function Spinner({ message, muted = true }: { message: ReactNode; muted?: boolean }) {
  return (
    <div style={{ textAlign: "center", padding: "40px 0" }}>
      <span className="spinner" style={{ width: 28, height: 28 }} />
      <p style={{ marginTop: 16, ...(muted ? { color: "var(--text-muted)" } : {}) }}>
        {message}
      </p>
    </div>
  );
}
