import { contextBridge, ipcRenderer } from "electron";

export type EmusyncConfig = {
  server_host?: string;
  server_port?: number;
  data_dir?: string;
  device_id?: string;
  device_name?: string;
  token?: string;
  is_server?: boolean;
};

contextBridge.exposeInMainWorld("emusync", {
  config: {
    load: (): Promise<EmusyncConfig | null> => ipcRenderer.invoke("config:load"),
    save: (data: EmusyncConfig): Promise<boolean> => ipcRenderer.invoke("config:save", data),
    exists: (): Promise<boolean> => ipcRenderer.invoke("config:exists"),
    getRecentFolders: (consoleKey: string): Promise<string[]> => ipcRenderer.invoke("config:getRecentFolders", consoleKey),
    addRecentFolder: (consoleKey: string, folderPath: string): Promise<void> => ipcRenderer.invoke("config:addRecentFolder", consoleKey, folderPath),
  },
  server: {
    start: (): Promise<{ ok: boolean; token: string | null }> =>
      ipcRenderer.invoke("server:start"),
    stop: (): Promise<boolean> => ipcRenderer.invoke("server:stop"),
    token: (): Promise<string | null> => ipcRenderer.invoke("server:token"),
    changePin: (pin: string | null): Promise<{ ok: boolean; token: string | null }> =>
      ipcRenderer.invoke("server:change-pin", pin),
    discover: (): Promise<Array<{ name: string; host: string; port: number }>> =>
      ipcRenderer.invoke("server:discover"),
    localIp: (): Promise<string | null> => ipcRenderer.invoke("server:local-ip"),
  },
  launcher: {
    path: (): Promise<string> => ipcRenderer.invoke("launcher:path"),
  },
  dialog: {
    openFile: (options?: { title?: string; filters?: { name: string; extensions: string[] }[] }): Promise<string | null> =>
      ipcRenderer.invoke("dialog:openFile", {
        properties: ["openFile"],
        ...options,
      }),
    openFolder: (): Promise<string | null> => ipcRenderer.invoke("dialog:openFolder"),
  },
  emulator: {
    consoles: (): Promise<{ key: string; label: string }[]> =>
      ipcRenderer.invoke("emulator:consoles"),
    detect: (consoleKey: string): Promise<{
      options: import("../../../electron/main").DetectedEmulatorOption[];
      suggestions: string[];
    }> => ipcRenderer.invoke("emulator:detect", consoleKey),
    scan: (
      consoleKey: string,
      emulatorOption: import("../../../electron/main").DetectedEmulatorOption,
      extraPaths: string[],
    ): Promise<import("../../../electron/main").EmulatorScanResult> =>
      ipcRenderer.invoke("emulator:scan", { consoleKey, emulatorOption, extraPaths }),
  },
  files: {
    ensureSave: (savePath: string): Promise<{ created: boolean }> =>
      ipcRenderer.invoke("files:ensure-save", savePath),
    getSaveTime: (savePath: string): Promise<string | null> =>
      ipcRenderer.invoke("files:get-save-time", savePath),
    getLatestInFolder: (dirPath: string): Promise<{ path: string; time: string } | null> =>
      ipcRenderer.invoke("files:get-latest-in-folder", dirPath),
    moveToSubfolder: (args: { romPath: string; subfolderName: string; newSavePath: string; newStateFolder: string }): Promise<{ ok: boolean; newRomPath: string; newSavePath: string; newStateFolder: string; error?: string }> =>
      ipcRenderer.invoke("files:move-to-subfolder", args),
  },
  save: {
    push: (slug: string, savePath: string): Promise<{ ok: boolean; error?: string }> =>
      ipcRenderer.invoke("save:push", slug, savePath),
    pull: (slug: string, savePath: string): Promise<{ ok: boolean; pulled: boolean; error?: string }> =>
      ipcRenderer.invoke("save:pull", slug, savePath),
  },
  state: {
    push: (slug: string, statePath: string): Promise<{ ok: boolean; error?: string }> =>
      ipcRenderer.invoke("state:push", slug, statePath),
    pull: (slug: string, statePath: string): Promise<{ ok: boolean; pulled: boolean; error?: string }> =>
      ipcRenderer.invoke("state:pull", slug, statePath),
  },
  device: {
    probe: (ip: string, port: number): Promise<boolean> =>
      ipcRenderer.invoke("device:probe", ip, port),
  },
  rom: {
    push: (slug: string, toDeviceId: string, consoleName: string): Promise<{ ok: boolean; targetOnline?: boolean; error?: string }> =>
      ipcRenderer.invoke("rom:push", slug, toDeviceId, consoleName),
  },
  game: {
    launch: (slug: string, command: string): Promise<{ ok: boolean }> =>
      ipcRenderer.invoke("game:launch", slug, command),
    stop: (): Promise<{ ok: boolean }> => ipcRenderer.invoke("game:stop"),
    isRunning: (): Promise<boolean> => ipcRenderer.invoke("game:isRunning"),
    stopExternal: (): Promise<{ ok: boolean }> => ipcRenderer.invoke("game:stop-external"),
    hasPidFile: (): Promise<boolean> => ipcRenderer.invoke("game:hasPidFile"),
    pushToServer: (slug: string): Promise<{ ok: boolean }> =>
      ipcRenderer.invoke("game:pushToServer", slug),
    onExited: (cb: () => void): void => { ipcRenderer.on("game:exited", cb); },
    offExited: (cb: () => void): void => { ipcRenderer.removeListener("game:exited", cb); },
  },
});
