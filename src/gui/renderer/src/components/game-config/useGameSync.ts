import { useCallback, useEffect, useRef, useState } from "react";
import {
  getConsoleMemcardMeta, getGameDevice, getSaveMeta, getStateMeta,
  checkSaveConflict, checkStateConflict, type SaveMeta, type ConflictCheck,
} from "../../api";
import { IDLE_OP, type SyncOp } from "./SyncLine";

// Save/state/memcard sync status + push/pull handlers for GameConfig's sync
// panels. A shared-layout console (PS2) has no per-game save/state to push or
// pull — its card + states sync automatically via `emusync run` — so callers
// gate the panels on `sharedLayout` themselves; this hook still tracks the
// console-scoped memcard meta whenever `sharedLayout` is true.
export function useGameSync(
  slug: string | null, savePath: string, statePath: string, gameConsole: string, sharedLayout: boolean,
) {
  const [localSaveTime, setLocalSaveTime] = useState<string | null>(null);
  const [serverSaveMeta, setServerSaveMeta] = useState<SaveMeta>(null);
  const [latestStateFile, setLatestStateFile] = useState<{ path: string; time: string } | null>(null);
  const [serverStateMeta, setServerStateMeta] = useState<SaveMeta>(null);
  const [saveOp, setSaveOp] = useState<SyncOp>(IDLE_OP);
  const [stateOp, setStateOp] = useState<SyncOp>(IDLE_OP);
  const [serverMemcardMeta, setServerMemcardMeta] = useState<SaveMeta>(null);
  const [memcardOp, setMemcardOp] = useState<SyncOp>(IDLE_OP);

  // Conflict modal state (issue #579).
  const [conflictModal, setConflictModal] = useState<{
    open: boolean;
    kind: "save" | "state";
    localHash: string;
    serverHash: string;
    serverPushedAt: string;
  } | null>(null);
  const conflictResolverRef = useRef<((winner: "local" | "server") => void) | null>(null);

  const loadSyncInfo = useCallback(async () => {
    if (!slug) return;
    const [sm, ss] = await Promise.allSettled([getSaveMeta(slug), getStateMeta(slug)]);
    if (sm.status === "fulfilled") setServerSaveMeta(sm.value);
    if (ss.status === "fulfilled") setServerStateMeta(ss.value);
    if (sharedLayout) {
      const mc = await getConsoleMemcardMeta(gameConsole).catch(() => null);
      setServerMemcardMeta(mc);
    }
  }, [slug, sharedLayout, gameConsole]);

  useEffect(() => {
    if (!savePath) return;
    window.emusync.files.getSaveTime(savePath).then(setLocalSaveTime).catch(() => {});
  }, [savePath]);

  useEffect(() => {
    if (!statePath) return;
    // statePath is now the state FOLDER itself
    window.emusync.files.getLatestInFolder(statePath).then(setLatestStateFile).catch(() => {});
  }, [statePath]);

  useEffect(() => { loadSyncInfo(); }, [loadSyncInfo]);

  // ── conflict check (issue #579) ─────────────────────────────────────────────

  /** Check for divergence and show the modal if both sides moved past baseline.
   *  Returns the resolved action: 'push', 'pull', or 'noop'. */
  async function checkConflictForAction(
    slug: string,
    path: string,
    kind: "save" | "state",
    intendedAction: "push" | "pull",
  ): Promise<"push" | "pull" | "noop"> {
    // Get the local hash
    const localHash = await window.emusync.files.getFileHash(path).catch(() => null);
    if (!localHash) return intendedAction; // can't hash → proceed with intended action

    // Check divergence
    const checkFn = kind === "save" ? checkSaveConflict : checkStateConflict;
    const result: ConflictCheck = await checkFn(slug, localHash).catch(() => ({ diverged: false }));

    if (!result.diverged) return intendedAction;

    // Show conflict modal — will resolve via setConflictModal + handleConflictChoice
    return new Promise<"push" | "pull" | "noop">((resolve) => {
      setConflictModal({
        open: true,
        kind,
        localHash,
        serverHash: result.server_hash!,
        serverPushedAt: result.server_pushed_at!,
      });
      conflictResolverRef.current = (winner: "local" | "server") => {
        setConflictModal(null);
        conflictResolverRef.current = null;
        if (winner === "local") {
          resolve(intendedAction === "push" ? "push" : "noop"); // keep local
        } else {
          resolve("pull"); // use server
        }
      };
    });
  }

  function handleConflictChoice(winner: "local" | "server"): void {
    conflictResolverRef.current?.(winner);
  }

  async function handlePushSave(): Promise<void> {
    if (!slug || !savePath) return;
    setSaveOp({ status: "busy", action: "push", msg: "" });
    const action = await checkConflictForAction(slug, savePath, "save", "push");
    if (action === "noop") {
      setSaveOp({ status: "ok", action: "push", msg: "Kept local version (server outdated)" });
      return;
    }
    const result = await window.emusync.save.push(slug, savePath);
    if (result.ok) {
      setSaveOp({ status: "ok", action: "push", msg: "Pushed to server" });
      await loadSyncInfo();
      const t = await window.emusync.files.getSaveTime(savePath).catch(() => null);
      setLocalSaveTime(t);
    } else {
      setSaveOp({ status: "error", action: "push", msg: result.error || "Push failed" });
    }
  }

  // Switch-only: this device has no local save yet, so there's no savePath
  // to pull *into* — seeds the server's save into whatever local Eden profile
  // exists and persists the resulting path server-side (#456 follow-up).
  // Returns the newly-adopted save path so the caller can pick it up, since
  // savePath itself lives in GameConfig's state, not here.
  async function handleSeedSwitchSave(): Promise<string | null> {
    if (!slug) return null;
    setSaveOp({ status: "busy", action: "pull", msg: "" });
    const result = await window.emusync.save.pullSwitchSeed(slug);
    if (!result.ok) {
      setSaveOp({ status: "error", action: "pull", msg: result.error || "No server save yet" });
      return null;
    }
    const gd = await getGameDevice(slug).catch(() => null);
    if (!gd?.save_path) {
      setSaveOp({ status: "error", action: "pull", msg: "Pulled, but couldn't resolve the save path" });
      return null;
    }
    setSaveOp({ status: "ok", action: "pull", msg: "Pulled from server" });
    await loadSyncInfo();
    const t = await window.emusync.files.getSaveTime(gd.save_path).catch(() => null);
    setLocalSaveTime(t);
    return gd.save_path;
  }

  async function handlePullSave(): Promise<void> {
    if (!slug || !savePath) return;
    setSaveOp({ status: "busy", action: "pull", msg: "" });
    const action = await checkConflictForAction(slug, savePath, "save", "pull");
    if (action === "noop") {
      setSaveOp({ status: "ok", action: "pull", msg: "Kept local version (skipped pull)" });
      return;
    }
    const result = await window.emusync.save.pull(slug, savePath);
    if (result.ok) {
      if (result.pulled) {
        setSaveOp({ status: "ok", action: "pull", msg: "Pulled — previous save backed up to .bak" });
        const t = await window.emusync.files.getSaveTime(savePath).catch(() => null);
        setLocalSaveTime(t);
      } else {
        setSaveOp({ status: "ok", action: "pull", msg: "No server save yet" });
      }
    } else {
      setSaveOp({ status: "error", action: "pull", msg: result.error || "Pull failed" });
    }
  }

  async function handlePushMemcard(): Promise<void> {
    if (!savePath || !gameConsole) return;
    setMemcardOp({ status: "busy", action: "push", msg: "" });
    const result = await window.emusync.memcard.push(gameConsole, savePath);
    if (result.ok) {
      setMemcardOp({ status: "ok", action: "push", msg: "Pushed to server" });
      await loadSyncInfo();
    } else {
      setMemcardOp({ status: "error", action: "push", msg: result.error || "Push failed" });
    }
  }

  async function handlePullMemcard(): Promise<void> {
    if (!savePath || !gameConsole) return;
    setMemcardOp({ status: "busy", action: "pull", msg: "" });
    const result = await window.emusync.memcard.pull(gameConsole, savePath);
    if (result.ok) {
      if (result.pulled) {
        setMemcardOp({ status: "ok", action: "pull", msg: "Pulled — previous card backed up to .bak" });
        const t = await window.emusync.files.getSaveTime(savePath).catch(() => null);
        setLocalSaveTime(t);
      } else {
        setMemcardOp({ status: "ok", action: "pull", msg: "No server card yet" });
      }
    } else {
      setMemcardOp({ status: "error", action: "pull", msg: result.error || "Pull failed" });
    }
  }

  async function handlePushState(): Promise<void> {
    if (!slug || !statePath) return;
    setStateOp({ status: "busy", action: "push", msg: "" });
    // For state folders, hash the latest file (not the whole folder)
    const latest = await window.emusync.files.getLatestInFolder(statePath).catch(() => null);
    const statePathForHash = latest?.path || statePath;
    const action = await checkConflictForAction(slug, statePathForHash, "state", "push");
    if (action === "noop") {
      setStateOp({ status: "ok", action: "push", msg: "Kept local version (server outdated)" });
      return;
    }
    const result = await window.emusync.state.push(slug, statePath);
    if (result.ok) {
      setStateOp({ status: "ok", action: "push", msg: "Pushed to server" });
      await loadSyncInfo();
      const updated = await window.emusync.files.getLatestInFolder(statePath).catch(() => null);
      setLatestStateFile(updated);
    } else {
      setStateOp({ status: "error", action: "push", msg: result.error || "Push failed" });
    }
  }

  async function handlePullState(): Promise<void> {
    if (!slug || !statePath) return;
    setStateOp({ status: "busy", action: "pull", msg: "" });
    const latest = await window.emusync.files.getLatestInFolder(statePath).catch(() => null);
    const statePathForHash = latest?.path || statePath;
    const action = await checkConflictForAction(slug, statePathForHash, "state", "pull");
    if (action === "noop") {
      setStateOp({ status: "ok", action: "pull", msg: "Kept local version (skipped pull)" });
      return;
    }
    const result = await window.emusync.state.pull(slug, statePath);
    if (result.ok) {
      if (result.pulled) {
        setStateOp({ status: "ok", action: "pull", msg: "Pulled — previous state backed up to .bak" });
        const updated = await window.emusync.files.getLatestInFolder(statePath).catch(() => null);
        setLatestStateFile(updated);
      } else {
        setStateOp({ status: "ok", action: "pull", msg: "No server state yet" });
      }
    } else {
      setStateOp({ status: "error", action: "pull", msg: result.error || "Pull failed" });
    }
  }

  return {
    localSaveTime, serverSaveMeta, latestStateFile, serverStateMeta,
    saveOp, stateOp, serverMemcardMeta, memcardOp,
    conflictModal, handleConflictChoice,
    loadSyncInfo, handlePushSave, handlePullSave, handleSeedSwitchSave,
    handlePushMemcard, handlePullMemcard, handlePushState, handlePullState,
  };
}
