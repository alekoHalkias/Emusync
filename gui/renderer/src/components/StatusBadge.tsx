import React, { useEffect, useState } from "react";
import { health } from "../api";

export default function StatusBadge(): React.ReactElement {
  const [online, setOnline] = useState<boolean | null>(null);

  useEffect(() => {
    let alive = true;

    async function check(): Promise<void> {
      const ok = await health();
      if (alive) setOnline(ok);
    }

    check();
    const id = setInterval(check, 5000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  if (online === null) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text-muted)" }}>
        <span className="spinner" />
        Checking server…
      </div>
    );
  }

  return (
    <div
      style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}
      title={online ? "EmuSync server is reachable" : "Is your gaming PC on and EmuSync server running?"}
    >
      <span
        style={{
          display: "inline-block",
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: online ? "var(--green)" : "var(--text-muted)",
        }}
      />
      <span style={{ color: online ? "var(--green)" : "var(--text-muted)" }}>
        {online ? "Server online" : "Server offline"}
      </span>
    </div>
  );
}
