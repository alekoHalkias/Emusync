import React, { useState } from "react";
import Modal from "./Modal";
import type { LocalCandidate } from "./game-list/useBrokenRoms";
import { uploadLocalRom } from "./game-config/localToNetwork";

type Props = { candidates: LocalCandidate[]; onClose: (changed: boolean) => void };

/** Refresh-locations prompt (#626): move local-only games into the console's default folder and/or add them to the network drive. */
export default function LocalToNetworkModal({ candidates, onClose }: Props): React.ReactElement {
  const movable = candidates.filter((c) => c.canMove);
  const uploadable = candidates.filter((c) => c.canUpload);
  const [doMove, setDoMove] = useState(movable.length > 0);
  const [doUpload, setDoUpload] = useState(uploadable.length > 0);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [errors, setErrors] = useState<string[]>([]);
  const [done, setDone] = useState(false);

  async function run(): Promise<void> {
    setBusy(true);
    const errs: string[] = [];
    let n = 0;
    for (const c of candidates) {
      setStatus(`${++n}/${candidates.length}: ${c.game.name}`);
      try {
        let romPath = c.game.romPath ?? "";
        if (doMove && c.canMove) {
          const m = await window.emusync.rom.moveToConsoleFolder(c.game.slug);
          if (!m.ok) { errs.push(`${c.game.name}: ${m.error ?? "move failed"}`); continue; }
          romPath = m.romPath ?? romPath;
        }
        if (doUpload && c.canUpload) {
          const u = await uploadLocalRom(c.game.slug, romPath, c.folder, c.netFolder);
          if (!u.ok) errs.push(`${c.game.name}: ${u.error}`);
        }
      } catch (e) {
        errs.push(`${c.game.name}: ${e instanceof Error ? e.message : String(e)}`);
      }
    }
    setErrors(errs);
    setStatus(`Finished ${candidates.length - errs.length} of ${candidates.length}.`);
    setDone(true);
    setBusy(false);
  }

  return (
    <Modal busy={busy} onClose={() => onClose(done)}>
      <h3>Local-only games found</h3>
      <p>{candidates.length} game{candidates.length !== 1 ? "s" : ""} exist only on this device. What would you like to do?</p>
      <ul style={{ maxHeight: 160, overflowY: "auto", fontSize: 13, paddingLeft: 18 }}>
        {candidates.map((c) => <li key={c.game.slug}>{c.game.name}</li>)}
      </ul>
      {!done && (
        <>
          {movable.length > 0 && (
            <label style={{ display: "block" }}>
              <input type="checkbox" checked={doMove} disabled={busy} onChange={(e) => setDoMove(e.target.checked)} /> Move {movable.length} into the console's default folder
            </label>
          )}
          {uploadable.length > 0 && (
            <label style={{ display: "block" }}>
              <input type="checkbox" checked={doUpload} disabled={busy} onChange={(e) => setDoUpload(e.target.checked)} /> Add {uploadable.length} to the network drive
            </label>
          )}
        </>
      )}
      {status && <p style={{ fontSize: 13, color: "var(--text-muted)" }}>{status}</p>}
      {errors.map((e) => <p key={e} role="alert" style={{ fontSize: 13, color: "var(--color-danger, #e5484d)" }}>{e}</p>)}
      <div className="modal-actions">
        <button className="btn btn-ghost" onClick={() => onClose(done)} disabled={busy}>{done ? "Close" : "Not now"}</button>
        {!done && <button className="btn btn-primary" onClick={run} disabled={busy || (!doMove && !doUpload)}>{busy ? "Working..." : "Apply"}</button>}
      </div>
    </Modal>
  );
}
