import { useCallback, useEffect, useState } from "react";
import { getConsoleMemcardMeta, getSaveMeta, getStateMeta, type SaveMeta } from "../../api";
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

  async function handlePushSave(): Promise<void> {
    if (!slug || !savePath) return;
    setSaveOp({ status: "busy", action: "push", msg: "" });
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

  async function handlePullSave(): Promise<void> {
    if (!slug || !savePath) return;
    setSaveOp({ status: "busy", action: "pull", msg: "" });
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
    const result = await window.emusync.state.push(slug, statePath);
    if (result.ok) {
      setStateOp({ status: "ok", action: "push", msg: "Pushed to server" });
      await loadSyncInfo();
      const latest = await window.emusync.files.getLatestInFolder(statePath).catch(() => null);
      setLatestStateFile(latest);
    } else {
      setStateOp({ status: "error", action: "push", msg: result.error || "Push failed" });
    }
  }

  async function handlePullState(): Promise<void> {
    if (!slug || !statePath) return;
    setStateOp({ status: "busy", action: "pull", msg: "" });
    const result = await window.emusync.state.pull(slug, statePath);
    if (result.ok) {
      if (result.pulled) {
        setStateOp({ status: "ok", action: "pull", msg: "Pulled — previous state backed up to .bak" });
        const latest = await window.emusync.files.getLatestInFolder(statePath).catch(() => null);
        setLatestStateFile(latest);
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
    loadSyncInfo, handlePushSave, handlePullSave,
    handlePushMemcard, handlePullMemcard, handlePushState, handlePullState,
  };
}
