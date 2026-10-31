// "Ignored games" toggle + list for the console settings modal (#646). Unignoring
// applies immediately; the ROM shows up again on the next import scan.
import React, { useEffect, useState } from "react";
import { loadIgnoredRoms, saveIgnoredRoms } from "./console-import/ignoredRoms";

export default function IgnoredGamesPanel({ consoleKey }: { consoleKey: string }): React.ReactElement {
  const [paths, setPaths] = useState<string[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => { loadIgnoredRoms(consoleKey).then(setPaths).catch(() => setPaths([])); }, [consoleKey]);

  const update = (next: string[]): void => { setPaths(next); void saveIgnoredRoms(consoleKey, next); };

  return (
    <div style={{ marginBottom: 12 }}>
      <button type="button" className="btn btn-ghost" onClick={() => setOpen((v) => !v)}>
        Ignored games ({paths.length})
      </button>
      {open && (
        <div style={{ marginTop: 8 }}>
          {paths.length === 0 && <p style={{ color: "var(--text-muted)", fontSize: 12, margin: 0 }}>No ignored games.</p>}
          {paths.map((p) => (
            <div key={p} style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 4 }}>
              <span title={p} style={{ flex: 1, overflowWrap: "anywhere", fontSize: 12 }}>{p}</span>
              <button className="btn btn-ghost" onClick={() => update(paths.filter((x) => x !== p))}>Unignore</button>
            </div>
          ))}
          {paths.length > 1 && (
            <button className="btn btn-ghost" onClick={() => update([])}>Unignore all</button>
          )}
        </div>
      )}
    </div>
  );
}
