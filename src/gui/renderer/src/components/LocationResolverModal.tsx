import React, { useState } from "react";
import Modal from "./Modal";
import type { GameRow } from "./game-list/types";

type Props = {
  game: GameRow;
  onClose: () => void;
  /** Resolves once the new path is saved; the caller launches the game afterwards. */
  onLocated: (newPath: string) => Promise<void>;
};

/** Play-time prompt when a game's ROM is missing from its saved location (issue #616). */
export default function LocationResolverModal({ game, onClose, onLocated }: Props): React.ReactElement {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isFolder = game.console === "switch"; // whole-folder ROMs (#441)

  async function locate(): Promise<void> {
    const picked = isFolder
      ? await window.emusync.dialog.openFolder()
      : await window.emusync.dialog.openFile({ title: `Locate ${game.name}` });
    if (!picked) return;
    setBusy(true);
    setError(null);
    try {
      await onLocated(picked);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <Modal busy={busy} onClose={onClose}>
      <h3>ROM not found</h3>
      <p>The ROM for <strong>{game.name}</strong> could not be found. Please locate the {isFolder ? "folder" : "file"}.</p>
      {game.romPath && <p style={{ fontSize: 12, color: "var(--text-muted)", wordBreak: "break-all" }}>{game.romPath}</p>}
      {error && <p role="alert" style={{ color: "var(--color-danger, #e5484d)" }}>{error}</p>}
      <div className="modal-actions">
        <button className="btn btn-ghost" onClick={onClose} disabled={busy}>Cancel</button>
        <button className="btn btn-primary" onClick={locate} disabled={busy}>{busy ? "Updating..." : `Locate ${isFolder ? "folder" : "file"}`}</button>
      </div>
    </Modal>
  );
}
