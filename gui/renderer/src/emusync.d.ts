// Ambient type for the Electron IPC bridge exposed by gui/electron/preload.ts.
// This is the single source of truth for `window.emusync` in the renderer —
// keep it in sync with preload.ts when channels change.
//
// `config.load`/`save` and the `emulator.detect`/`scan` returns are kept loose
// on purpose (the config is an open TOML dict, and the emulator result types
// live in the electron package); tightening those is tracked separately.

/** A `.bak` loser found on local disk (issue #285). */
export interface LocalBak {
  path: string;
  kind: "save" | "state";
  size: number;
  mtime: string;
  fileName: string;
}

export interface EmusyncBridge {
  config: {
    load: () => Promise<Record<string, any> | null>;
    save: (data: Record<string, any>) => Promise<boolean>;
    exists: () => Promise<boolean>;
    getRecentFolders: (consoleKey: string) => Promise<string[]>;
    addRecentFolder: (consoleKey: string, folderPath: string) => Promise<void>;
  };
  server: {
    start: () => Promise<{ ok: boolean; token: string | null }>;
    stop: () => Promise<boolean>;
    changePin: (pin: string | null) => Promise<{ ok: boolean; token: string | null }>;
    discover: () => Promise<Array<{ name: string; host: string; port: number }>>;
    localIp: () => Promise<string | null>;
  };
  launcher: {
    path: () => Promise<string>;
  };
  dialog: {
    openFile: (options?: { title?: string; filters?: { name: string; extensions: string[] }[] }) => Promise<string | null>;
    openFolder: () => Promise<string | null>;
  };
  emulator: {
    consoles: () => Promise<{ key: string; label: string; abbr?: string }[]>;
    detect: (consoleKey: string) => Promise<{ options: any[]; suggestions: string[] }>;
    scan: (consoleKey: string, emulatorOption: any, extraPaths: string[]) => Promise<{ emulators: any[]; romDirs: string[]; roms: any[] }>;
  };
  files: {
    ensureSave: (savePath: string) => Promise<{ created: boolean }>;
    getSaveTime: (savePath: string) => Promise<string | null>;
    getLatestInFolder: (dirPath: string) => Promise<{ path: string; time: string } | null>;
    getPs2LastPlayed: () => Promise<Record<string, string>>;
    renameGameFiles: (args: { romPath: string; savePath: string; stateFolder: string; newBase: string; reorganize: boolean; secondaryRomPath?: string }) => Promise<{ ok: boolean; newRomPath: string; newSavePath: string; newStateFolder: string; newSecondaryRomPath?: string; error?: string }>;
  };
  save: {
    push: (slug: string, savePath: string) => Promise<{ ok: boolean; error?: string }>;
    pull: (slug: string, savePath: string) => Promise<{ ok: boolean; pulled: boolean; error?: string }>;
  };
  state: {
    push: (slug: string, statePath: string) => Promise<{ ok: boolean; error?: string }>;
    pull: (slug: string, statePath: string) => Promise<{ ok: boolean; pulled: boolean; error?: string }>;
  };
  memcard: {
    push: (consoleKey: string, cardPath: string) => Promise<{ ok: boolean; error?: string }>;
    pull: (consoleKey: string, cardPath: string) => Promise<{ ok: boolean; pulled: boolean; error?: string }>;
  };
  device: {
    probe: (ip: string, port: number) => Promise<boolean>;
  };
  rom: {
    push: (slug: string, toDeviceId: string, consoleName: string) => Promise<{ ok: boolean; targetOnline?: boolean; error?: string }>;
    localize: (slug: string, destFolder?: string) => Promise<{ ok: boolean; localPath?: string; error?: string }>;
    delocalize: (slug: string) => Promise<{ ok: boolean; error?: string }>;
    uploadMaster: (localPath: string, networkPath: string) => Promise<{ ok: boolean; sha256?: string; skipped?: boolean; error?: string }>;
    setupNetworkPlay: (slug: string, mountRoot: string) => Promise<{ ok: boolean; romPath?: string; error?: string }>;
    deleteFile: (absolutePath: string) => Promise<{ ok: boolean; error?: string }>;
  };
  recovery: {
    listLocalBackups: (savePath: string, stateFolder: string) => Promise<{
      saves: LocalBak[];
      states: LocalBak[];
    }>;
    restoreLocalBackup: (bakPath: string, targetPath: string) => Promise<{ ok: boolean; error?: string }>;
  };
  art: {
    get: (slug: string, gameName: string, consoleKey: string) => Promise<string | null>;
    getConsoleIcon: (consoleKey: string) => Promise<string | null>;
  };
  artwork: {
    searchGames: (name: string) => Promise<{ id: number; name: string; release_date: number; verified: boolean }[]>;
    getMatchedGame: (sgdbGameId: number) => Promise<{ id: number; name: string } | null>;
    resolveMatch: (slug: string, gameName: string) => Promise<{ id: number; name: string } | null>;
    listCandidates: (sgdbGameId: number, type: "grid" | "hero" | "logo" | "icon" | "wide_grid") => Promise<{ id: number; thumb: string; url: string }[]>;
    setArt: (slug: string, consoleKey: string, type: "grid" | "hero" | "logo" | "icon" | "wide_grid", url: string) => Promise<{ ok: boolean; error?: string }>;
    clearArt: (slug: string, consoleKey: string, type: "grid" | "hero" | "logo" | "icon" | "wide_grid") => Promise<{ ok: boolean }>;
    getCurrent: (slug: string, consoleKey: string) => Promise<Record<"grid" | "hero" | "logo" | "icon" | "wide_grid", string | null>>;
    refreshAll: (slug: string, gameName: string, consoleKey: string, sgdbGameId: number | null) => Promise<Record<"grid" | "hero" | "logo" | "icon" | "wide_grid", boolean>>;
  };
  steamgriddb: {
    getKey: () => Promise<string | null>;
    setKey: (key: string) => Promise<{ ok: boolean; error?: string }>;
    openKeyPage: () => Promise<void>;
  };
  steam: {
    addGame: (slug: string, gameName: string, consoleName: string, consoleKey: string) => Promise<{ ok: boolean; updated?: boolean; warning?: string; error?: string }>;
    isAdded: (slug: string) => Promise<boolean>;
  };
  daemon: {
    start: () => Promise<void>;
    stop: () => Promise<void>;
  };
  game: {
    launch: (slug: string) => Promise<{ ok: boolean }>;
    stop: () => Promise<{ ok: boolean }>;
    isRunning: () => Promise<boolean>;
    stopExternal: () => Promise<{ ok: boolean }>;
    hasPidFile: () => Promise<boolean>;
    offlineList: () => Promise<{ slug: string; name: string; console: string; savePath?: string; statePath?: string }[]>;
    onExited: (cb: () => void) => void;
    offExited: (cb: () => void) => void;
  };
}

declare global {
  interface Window {
    emusync: EmusyncBridge;
  }
}
