// Post-import follow-up work for the Add-Console wizard: pull down any
// existing save/state from the server, pre-fetch artwork, and auto-push newly
// imported ROMs to paired devices (issues #316, #327, and the original
// auto-push behavior). Each function takes its React state setters as
// parameters rather than closing over hook state, so it has no dependency on
// useConsoleImport beyond the shared `window.emusync` bridge.
import { getConsoleMemcardMeta, getDeviceGameDevices, getSaveMeta, getStateMeta, listDevices, type Device, type SaveMeta } from "../../api";
import { usesSharedSaveLayout, usesSharedStateLayout } from "./helpers";
import type { ImportedEntry, PushResult } from "./types";
import { parseUtc } from "../../time";

// IPC bridge (typing deferred to the typed-bridge work in #228).
const emusync = window.emusync;

/** Whether `serverMeta`'s data is newer than the local file at `localTime`
 * (or there's no local file yet, in which case the server copy always wins).
 * Both timestamps are tz-less UTC strings — must go through parseUtc, not a
 * raw `new Date()`, or they're misread as local time (see time.tsx). */
export function _serverIsNewer(localTime: string | null, serverMeta: SaveMeta): boolean {
  if (!serverMeta) return false;
  const local = parseUtc(localTime);
  const server = parseUtc(serverMeta.pushed_at);
  return !local || (!!server && server > local);
}

export async function prefetchArt(
  entries: ImportedEntry[], consoleKey: string,
  setArtProgress: (v: { done: number; total: number }) => void,
): Promise<void> {
  setArtProgress({ done: 0, total: entries.length });
  for (let i = 0; i < entries.length; i++) {
    // All 5 types, not just the console's configured one (#411) — reuses the
    // Artwork tab's per-type SGDB dispatch (#325) instead of art:get's single
    // type, so switching a console's art-type dropdown or opening a game's
    // Artwork tab always has something cached. sgdbGameId is always null here:
    // a freshly-imported game has no match yet, so refreshAll resolves and
    // persists one (same auto-search behavior art:get already had, #339).
    // Sequential across games and, internally, across types — never more than
    // one SGDB request in flight — and each type's failure is isolated inside
    // refreshAll, so a rate-limited/missing type doesn't stop the rest.
    try { await emusync.artwork.refreshAll(entries[i].slug, entries[i].name, consoleKey, null); } catch { /* best-effort */ }
    setArtProgress({ done: i + 1, total: entries.length });
  }
}

export async function pullFromServerIfNewer(
  entries: ImportedEntry[], sharedLayout: boolean, sharedStateLayout: boolean, consoleAbbr: string,
): Promise<void> {
  if (sharedLayout) {
    // One card shared by every game on the console — pull it once. Every
    // entry's savePath resolves to the same physical card file (#295/#402).
    const cardPath = entries[0].savePath;
    if (cardPath) {
      try {
        const [meta, localTime] = await Promise.all([
          getConsoleMemcardMeta(consoleAbbr),
          emusync.files.getSaveTime(cardPath).catch(() => null),
        ]);
        if (_serverIsNewer(localTime, meta)) {
          await emusync.memcard.pull(consoleAbbr, cardPath);
        }
      } catch { /* best-effort */ }
    }
  }
  // Shared save STATES (PS2's serial-keyed sstates/) aren't pulled here:
  // there's no console-scoped state endpoint — only emusync run's per-launch,
  // serial-filtered sync touches them (#294). dc/gamecube/psp states are
  // normal per-game folders, so they pull below like any other console (#402).
  if (sharedLayout && sharedStateLayout) return;
  for (const entry of entries) {
    try {
      if (!sharedLayout && entry.savePath) {
        const [saveMeta, localTime] = await Promise.all([
          getSaveMeta(entry.slug),
          emusync.files.getSaveTime(entry.savePath).catch(() => null),
        ]);
        if (_serverIsNewer(localTime, saveMeta)) {
          await emusync.save.pull(entry.slug, entry.savePath);
        }
      }
      if (entry.statePath) {
        // state_path is a FOLDER (RetroArch content-dir layout) — its newest
        // file's time is the meaningful "local time", not the folder's own.
        const [stateMeta, latest] = await Promise.all([
          getStateMeta(entry.slug),
          emusync.files.getLatestInFolder(entry.statePath).catch(() => null),
        ]);
        if (_serverIsNewer(latest?.time ?? null, stateMeta)) {
          await emusync.state.pull(entry.slug, entry.statePath);
        }
      }
    } catch { /* best-effort — one game's pull failing shouldn't stop the rest */ }
  }
}

export async function autoPush(
  entries: ImportedEntry[], consoleAbbr: string,
  opts: { pushSaves: boolean; pushStates: boolean },
  setPushResults: (fn: (prev: PushResult[]) => PushResult[]) => void,
): Promise<void> {
  const sharedLayout = usesSharedSaveLayout(consoleAbbr);
  const sharedStateLayout = usesSharedStateLayout(consoleAbbr);
  const { pushSaves, pushStates } = opts;
  try {
    const cfg = await emusync.config.load();
    const myDeviceId: string = cfg?.device_id ?? "";
    const allDevices: Device[] = await listDevices();
    const others = allDevices.filter(d => d.id !== myDeviceId);
    if (others.length === 0) return;

    for (const device of others) {
      setPushResults(prev => [...prev, { deviceName: device.name, status: "pushing" }]);
      let ok = true;
      let offline = false;
      let errMsg = "";

      // Fetch this device's existing games once instead of per-entry.
      const deviceSlugs = new Set((await getDeviceGameDevices(device.id)).map(g => g.slug));

      for (const entry of entries) {
        // Skip if this device already has the game
        if (deviceSlugs.has(entry.slug)) continue;

        // Push ROM
        const romResult: { ok: boolean; targetOnline?: boolean; error?: string } =
          await emusync.rom.push(entry.slug, device.id, consoleAbbr);
        if (!romResult.ok) { ok = false; errMsg = romResult.error ?? "Push failed"; break; }
        if (romResult.targetOnline === false) offline = true;

        // Push save if user opted in and save file exists. Skipped for a
        // shared-save console (PS2/DC/GC/PSP): the card isn't per-game, so a
        // per-game save push would store the wrong thing — it syncs via
        // `emusync run`'s console-card path (#294/#295/#402).
        if (pushSaves && !sharedLayout) {
          const saveTime = await emusync.files.getSaveTime(entry.savePath);
          if (saveTime) {
            try { await emusync.save.push(entry.slug, entry.savePath); } catch { /* non-fatal */ }
          }
        }

        // Push state if user opted in and state folder has files. Only a
        // shared-STATE console (PS2) skips this — dc/gamecube/psp states are
        // normal per-game folders (#402).
        if (pushStates && !sharedStateLayout && entry.statePath) {
          const latest = await emusync.files.getLatestInFolder(entry.statePath);
          if (latest) {
            try { await emusync.state.push(entry.slug, entry.statePath); } catch { /* non-fatal */ }
          }
        }
      }

      setPushResults(prev => prev.map(r =>
        r.deviceName === device.name
          ? { ...r, status: ok ? (offline ? "offline" : "ok") : "error", error: errMsg }
          : r
      ));
    }
  } catch {
    // Server unreachable — silently skip auto-push
  }
}
