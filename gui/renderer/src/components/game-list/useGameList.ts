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

/**
 * Owns the game list data: the batched overview fetch, local save-time
 * enrichment, the initial load, and the 5s background poll.
 *
 * A monotonic `loadIdRef` guards against a slow in-flight request overwriting
 * the results of a newer one (e.g. a poll tick that started before a manual
 * reload but finished after it).
 */
export function useGameList(): UseGameList {
  const [games, setGames] = useState<GameRow[]>([]);
  const [loading, setLoading] = useState(true);
  const loadIdRef = useRef(0);
  // Flips to true after the first successful fetch; drives the poll cadence.
  const everLoadedRef = useRef(false);

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
      if (!silent) setLoading(false);
    } catch {
      if (loadIdRef.current !== thisId) return;
      if (silent) return; // background poll failed — keep showing current data
      if (!everLoadedRef.current) {
        // Server not yet ready during startup. Stay in loading=true; the
        // self-scheduling poll below retries in 1 s.
        setLoading(true);
        return;
      }
      // Server went offline after we had data — show empty / offline state.
      setGames([]);
      setLoading(false);
    }
  }, []);

  // Initial load on mount.
  useEffect(() => { reload(); }, [reload]);

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
