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
  },
  game: {
    launch: (slug: string, command: string): Promise<{ ok: boolean }> =>
      ipcRenderer.invoke("game:launch", slug, command),
    stop: (): Promise<{ ok: boolean }> => ipcRenderer.invoke("game:stop"),
    isRunning: (): Promise<boolean> => ipcRenderer.invoke("game:isRunning"),
    onExited: (cb: () => void): void => { ipcRenderer.on("game:exited", cb); },
    offExited: (cb: () => void): void => { ipcRenderer.removeListener("game:exited", cb); },
  },
});
