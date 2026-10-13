// Single-game "Copy for offline play" job (#520), kept outside React so it
// survives the settings panel unmounting (e.g. after "Hide"): the modal, the
// inline bar next to the button, and the topbar indicator all read this store.
import { useSyncExternalStore } from "react";
import { createSpeedMeter } from "./components/speedMeter";

export type LocalizeJob = {
  slug: string;
  gameName: string;
  doneBytes: number;
  totalBytes: number;
  speedBps: number;
  hidden: boolean;
  cancelling: boolean;
};

let job: LocalizeJob | null = null;
const listeners = new Set<() => void>();
const set = (next: LocalizeJob | null): void => { job = next; listeners.forEach((l) => l()); };
const patch = (p: Partial<LocalizeJob>): void => { if (job) set({ ...job, ...p }); };

export function useLocalizeJob(): LocalizeJob | null {
  return useSyncExternalStore(
    (cb) => { listeners.add(cb); return () => { listeners.delete(cb); }; },
    () => job,
  );
}

export const hideLocalizeJob = (hidden: boolean): void => patch({ hidden });

export function cancelLocalizeJob(): void {
  patch({ cancelling: true });
  window.emusync.rom.cancelLocalize().catch(() => {});
}

/** Runs the copy and resolves with the IPC result; one job at a time. */
export async function startLocalizeJob(slug: string, gameName: string, folder: string) {
  const sizes = await window.emusync.rom.localizeSizes([slug]).catch(() => ({} as Record<string, number>));
  const meter = createSpeedMeter();
  set({ slug, gameName, doneBytes: 0, totalBytes: sizes[slug] ?? 0, speedBps: 0, hidden: false, cancelling: false });
  const listener = window.emusync.rom.onLocalizeProgress((p) => {
    if (p.slug !== slug) return;
    patch({ doneBytes: p.copied, totalBytes: p.total, speedBps: meter.update(p.copied) });
  });
  try {
    return await window.emusync.rom.localize(slug, folder);
  } finally {
    window.emusync.rom.offLocalizeProgress(listener);
    set(null);
  }
}
