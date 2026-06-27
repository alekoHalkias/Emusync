import type { GameRow, SortBy, SortDir } from "./types";

/**
 * Group games by console name (falling back to "Other"), returning entries
 * sorted by console key. When sorting by game name descending, the console
 * order is reversed too so the whole list reads top-to-bottom consistently.
 */
export function groupByConsole(list: GameRow[], sortBy: SortBy, sortDir: SortDir): [string, GameRow[]][] {
  const grouped = list.reduce<Record<string, GameRow[]>>((acc, g) => {
    const key = g.console || "Other";
    (acc[key] ??= []).push(g);
    return acc;
  }, {});
  let keys = Object.keys(grouped).sort();
  if (sortBy === "game" && sortDir === "desc") keys = keys.reverse();
  return keys.map(k => [k, grouped[k]]);
}

/**
 * The most recent of a game's local save mtime and server sync time — the value
 * shown in the combined "Last Activity" column. ISO-8601 UTC strings compare
 * correctly lexically, so a string max is enough. Returns "" when neither is set.
 */
export function lastActivity(g: GameRow): string {
  const save = g.lastSave || "";
  const sync = g.lastPush || "";
  return save > sync ? save : sync;
}

/** Sort the games within a single console group. "default" leaves them untouched. */
export function sortGamesInConsole(consoleGames: GameRow[], sortBy: SortBy, sortDir: SortDir): GameRow[] {
  if (sortBy === "default") return consoleGames;

  const sorted = [...consoleGames];
  const mult = sortDir === "asc" ? 1 : -1;

  if (sortBy === "game") {
    sorted.sort((a, b) => mult * a.name.localeCompare(b.name));
  } else if (sortBy === "activity") {
    sorted.sort((a, b) => mult * lastActivity(a).localeCompare(lastActivity(b)));
  }

  return sorted;
}
