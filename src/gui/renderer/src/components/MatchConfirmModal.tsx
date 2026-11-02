import React, { useState } from "react";
import Modal from "./Modal";
import { updateRom, type MatchProposal } from "./game-list/useBrokenRoms";

type Row = MatchProposal & { name: string };
type Props = { proposals: Row[]; onClose: (changed: boolean, declined: string[]) => void };

/** Filename + size matches (#731): nothing is saved until the user ticks a row and clicks Link. */
export default function MatchConfirmModal({ proposals, onClose }: Props): React.ReactElement {
  const [picked, setPicked] = useState<Set<string>>(new Set(proposals.map((p) => p.slug)));
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [done, setDone] = useState(false);
  const [linked, setLinked] = useState(0);

  const unpicked = (): string[] => proposals.filter((p) => !picked.has(p.slug)).map((p) => p.slug);

  async function run(): Promise<void> {
    setBusy(true);
    const errs: string[] = [];
    let n = 0;
    for (const p of proposals.filter((x) => picked.has(x.slug))) {
      try {
        if (p.kind === "network") {
          const r = await window.emusync.rom.confirmNetworkMatch(p.slug, p.romPath, p.mountRoot ?? "");
          if (!r.ok) { errs.push(`${p.name}: ${r.error ?? "link failed"}`); continue; }
        } else {
          await updateRom(p.slug, p.romPath);
        }
        n++;
      } catch (e) {
        errs.push(`${p.name}: ${e instanceof Error ? e.message : String(e)}`);
      }
    }
    setErrors(errs);
    setLinked(n);
    setDone(true);
    setBusy(false);
  }

  const toggle = (slug: string): void =>
    setPicked((prev) => { const next = new Set(prev); if (next.has(slug)) next.delete(slug); else next.add(slug); return next; });

  return (
    <Modal busy={busy} onClose={() => onClose(done && linked > 0, done ? unpicked() : proposals.map((p) => p.slug))}>
      <h3>Possible game matches</h3>
      <p>These files have the same name and size as a game&apos;s ROM. Link the ones that are the same game.</p>
      <ul style={{ maxHeight: 220, overflowY: "auto", fontSize: 13, paddingLeft: 0, listStyle: "none" }}>
        {proposals.map((p) => (
          <li key={p.slug} style={{ marginBottom: 6 }}>
            <label>
              <input type="checkbox" checked={picked.has(p.slug)} disabled={busy || done} onChange={() => toggle(p.slug)} />{" "}
              {p.name} <span style={{ color: "var(--text-muted)" }}>({p.kind === "network" ? "network drive" : "moved ROM"})</span>
              <div style={{ fontSize: 12, color: "var(--text-muted)", marginLeft: 22, wordBreak: "break-all" }}>{p.romPath}</div>
            </label>
          </li>
        ))}
      </ul>
      {done && <p style={{ fontSize: 13, color: "var(--text-muted)" }}>Linked {linked} game{linked !== 1 ? "s" : ""}.</p>}
      {errors.map((e) => <p key={e} role="alert" style={{ fontSize: 13, color: "var(--color-danger, #e5484d)" }}>{e}</p>)}
      <div className="modal-actions">
        <button className="btn btn-ghost" onClick={() => onClose(done && linked > 0, done ? unpicked() : proposals.map((p) => p.slug))} disabled={busy}>
          {done ? "Close" : "Not now"}
        </button>
        {!done && <button className="btn btn-primary" onClick={run} disabled={busy || picked.size === 0}>{busy ? "Linking..." : "Link"}</button>}
      </div>
    </Modal>
  );
}
