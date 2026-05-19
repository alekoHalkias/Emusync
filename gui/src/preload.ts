import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("emusync", {
  checkConfig: (): Promise<{ configExists: boolean }> =>
    ipcRenderer.invoke("check-config"),

  getBackendPort: (): Promise<number> =>
    ipcRenderer.invoke("get-backend-port"),

  openFileDialog: (options?: object): Promise<string | null> =>
    ipcRenderer.invoke("open-file-dialog", options),

  openDirectoryDialog: (): Promise<string | null> =>
    ipcRenderer.invoke("open-directory-dialog"),
});
