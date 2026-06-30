import { useCallback, useEffect, useRef, useState } from "react";
import { gamesOverview } from "../../api";
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

  const reload = useCallback(async (silent = false) => {
    const thisId = ++loadIdRef.current;
    if (!silent) setLoading(true);
    try {
      // One batched request replaces the old per-game fan-out (save meta + lock +
      // device config). getSaveTime stays — it's a local fs stat, not a server call.
      const overview = await gamesOverview();
      const enriched = await Promise.all(
        overview.map(async (g): Promise<GameRow> => {
          let lastSave: string | null = null;
          if (g.is_local && g.save_path) {
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
      // Discard results from a superseded load (a newer call started while this was in flight)
      if (loadIdRef.current !== thisId) return;
      setGames(enriched);
    } catch {
      if (loadIdRef.current !== thisId) return;
      // Server offline — show empty list, StatusBadge shows the offline indicator
      if (!silent) setGames([]);
    } finally {
      if (loadIdRef.current !== thisId) return;
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => { reload(); }, [reload]);

  useEffect(() => {
    const id = setInterval(() => reload(true), 5000);
    return () => clearInterval(id);
  }, [reload]);

  return { games, loading, reload };
}
