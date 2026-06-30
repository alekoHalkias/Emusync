import type { Game } from "../../api";

/** A game row in the list, augmented with per-device sync metadata. */
export type GameRow = Game & {
  lastPush?: string;
  lastSave?: string | null;
  locked?: boolean;
  isLocal: boolean;
  savePath?: string;
  statePath?: string;          // local state FOLDER (issue #285 recovery view)
  romSource?: string;          // 'local' | 'network' (issue #255)
  hasLocalCopy?: boolean;      // network ROM that's been localized for offline play
};

/** State of an in-flight ROM push/pull to a single device, keyed by device id. */
export type TransferState = { status: "idle" | "loading" | "success" | "error"; message: string };

/** What the per-game device modal needs to identify and scope itself. */
export type DeviceModalTarget = {
  slug: string;
  name: string;
  gameConsole: string;
  gameIsLocal: boolean;          // true = current device has rom_path for this game
};

export type SortBy = "default" | "game" | "activity";
export type SortDir = "asc" | "desc";
