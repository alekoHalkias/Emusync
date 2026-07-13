import { useCallback, useEffect, useRef, useState } from "react";
import { gamesOverview } from "../../api";
import { usesSharedSaveLayout } from "../console-import/helpers";
import type { GameRow } from "./types";

export type UseGameList = {
  games: GameRow[];
  loading: boolean;
  /** Reload the list. Pass `silent` to refresh without toggling the loading spinner. */
  reload: (silent?: boolean) => Promise<void>;
};

// Instant warm-start cache (issue #410) — a plain localStorage entry, not one of
// the ~/.emusync/ files: this is a pure GUI paint-speed concern (skip the
// loading spinner while the poll below silently reconciles), not cross-process
// state the CLI needs to see. Bump the version suffix if GameRow's shape
// changes incompatibly.
const CACHE_KEY = "emusync.gameListCache.v1";

function readCache(): GameRow[] | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : null;
  } catch {
    return null; // corrupt JSON, storage disabled, quota — always degrade to "no cache"
  }
}

function writeCache(rows: GameRow[]): void {
  try { localStorage.setItem(CACHE_KEY, JSON.stringify(rows)); } catch { /* best-effort */ }
}

/**
 * Owns the game list data: the batched overview fetch, local save-time
 * enrichment, the initial load, and the 5s background poll.
 *
 * A monotonic `loadIdRef` guards against a slow in-flight request overwriting
 * the results of a newer one (e.g. a poll tick that started before a manual
 * reload but finished after it).
 */
export function useGameList(): UseGameList {
  // Read once per mount (React only invokes a useState initializer function
  // once, even under StrictMode's double-render) and share the result with
  // the two other pieces of state that depend on whether a cache existed.
  const [cached] = useState<GameRow[] | null>(readCache);
  const [games, setGames] = useState<GameRow[]>(cached ?? []);
  const [loading, setLoading] = useState(cached === null);
  const loadIdRef = useRef(0);
  // Flips to true after the first successful fetch; drives the poll cadence.
  // Seeded true when a warm cache exists, so the initial fetch runs silently
  // (no spinner flash over the cached view) and a failure just keeps showing
  // the cached rows instead of falling through to the offline-list fallback.
  const everLoadedRef = useRef(cached !== null);

  const reload = useCallback(async (silent = false) => {
    const thisId = ++loadIdRef.current;
    if (!silent) setLoading(true);
    try {
      // One batched request replaces the old per-game fan-out (save meta + lock +
      // device config). getSaveTime stays — it's a local fs stat, not a server call.
      const overview = await gamesOverview();
      // PS2 games share one memory card, so its mtime is meaningless per-game.
      // Use PCSX2's real per-game last-played (playtime.dat) as their activity (#301).
      const ps2LastPlayed = await window.emusync.files.getPs2LastPlayed().catch(() => ({} as Record<string, string>));
      const enriched = await Promise.all(
        overview.map(async (g): Promise<GameRow> => {
          const sharedLayout = usesSharedSaveLayout(g.console);
          let lastSave: string | null = null;
          if (sharedLayout) {
            lastSave = ps2LastPlayed[g.slug] ?? null;
          } else if (g.is_local && g.save_path) {
            lastSave = await window.emusync.files.getSaveTime(g.save_path);
          }
          return {
            slug: g.slug,
            name: g.name,
            console: g.console,
            lastPush: g.last_push ?? undefined,
            lastSave,
            locked: g.locked,
            isLocal: g.is_local,
            savePath: g.save_path || undefined,
            statePath: g.state_path || undefined,
            romSource: g.rom_source,
            hasLocalCopy: g.rom_source === "network" && !!g.local_rom_path,
          };
        })
      );
      if (loadIdRef.current !== thisId) return;
      everLoadedRef.current = true;
      setGames(enriched);
      writeCache(enriched);
      if (!silent) setLoading(false);
    } catch {
      if (loadIdRef.current !== thisId) return;
      if (silent) return; // background poll failed — keep showing current data
      if (!everLoadedRef.current) {
        // Never reached the server (e.g. app opened while it's off/unreachable).
        // Fall back to whatever this device cached from its last online launch of
        // each game, so the user can still find and press Play (issue #383) — the
        // CLI's offline-launch path already holds the save and reconciles it on
        // the next online launch. Keep polling in the background so live data
        // takes over the moment the server becomes reachable.
        const offlineGames = await window.emusync.game.offlineList().catch(() => []);
        if (loadIdRef.current !== thisId) return;
        if (offlineGames.length > 0) {
          setGames(offlineGames.map((g): GameRow => ({
            slug: g.slug,
            name: g.name,
            console: g.console,
            isLocal: true,
            locked: false,
            savePath: g.savePath,
            statePath: g.statePath,
            offline: true,
          })));
          everLoadedRef.current = true;
          setLoading(false);
          return;
        }
        // Nothing cached either. Stay in loading=true; the self-scheduling poll
        // below retries in 1 s.
        setLoading(true);
        return;
      }
      // Server went offline after we had data — show empty / offline state.
      setGames([]);
      setLoading(false);
    }
  }, []);

  // Initial load on mount. Silent when a warm cache already primed the view
  // (everLoadedRef seeded true above), so this fetch never flashes a spinner
  // over the cached rows; unchanged (non-silent) on a genuinely cold start.
  useEffect(() => { reload(everLoadedRef.current); }, [reload]);

  // Self-scheduling poll: 1 s until first success, then 5 s.
  // Using setTimeout (not setInterval) so the delay adapts after each tick.
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    function tick(): void {
      timer = setTimeout(async () => {
        await reload(everLoadedRef.current);
        tick();
      }, everLoadedRef.current ? 5000 : 1000);
    }
    tick();
    return () => clearTimeout(timer);
  }, [reload]);

  return { games, loading, reload };
}
