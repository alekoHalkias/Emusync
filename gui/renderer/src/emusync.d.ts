// Ambient type for the Electron IPC bridge exposed by gui/electron/preload.ts.
// This is the single source of truth for `window.emusync` in the renderer —
// keep it in sync with preload.ts when channels change.
//
// `config.load`/`save` and the `emulator.detect`/`scan` returns are kept loose
// on purpose (the config is an open TOML dict, and the emulator result types
// live in the electron package); tightening those is tracked separately.

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
    token: () => Promise<string | null>;
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
    consoles: () => Promise<{ key: string; label: string }[]>;
    detect: (consoleKey: string) => Promise<{ options: any[]; suggestions: string[] }>;
    scan: (consoleKey: string, emulatorOption: any, extraPaths: string[]) => Promise<{ emulators: any[]; romDirs: string[]; roms: any[] }>;
  };
  files: {
    ensureSave: (savePath: string) => Promise<{ created: boolean }>;
    getSaveTime: (savePath: string) => Promise<string | null>;
    getLatestInFolder: (dirPath: string) => Promise<{ path: string; time: string } | null>;
    moveToSubfolder: (args: { romPath: string; subfolderName: string; newSavePath: string; newStateFolder: string }) => Promise<{ ok: boolean; newRomPath: string; newSavePath: string; newStateFolder: string; error?: string }>;
  };
  save: {
    push: (slug: string, savePath: string) => Promise<{ ok: boolean; error?: string }>;
    pull: (slug: string, savePath: string) => Promise<{ ok: boolean; pulled: boolean; error?: string }>;
  };
  state: {
    push: (slug: string, statePath: string) => Promise<{ ok: boolean; error?: string }>;
    pull: (slug: string, statePath: string) => Promise<{ ok: boolean; pulled: boolean; error?: string }>;
  };
  device: {
    probe: (ip: string, port: number) => Promise<boolean>;
  };
  rom: {
    push: (slug: string, toDeviceId: string, consoleName: string) => Promise<{ ok: boolean; targetOnline?: boolean; error?: string }>;
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
    onExited: (cb: () => void) => void;
    offExited: (cb: () => void) => void;
  };
}

declare global {
  interface Window {
    emusync: EmusyncBridge;
  }
}
