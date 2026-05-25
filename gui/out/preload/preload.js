"use strict";
const electron = require("electron");
electron.contextBridge.exposeInMainWorld("emusync", {
  config: {
    load: () => electron.ipcRenderer.invoke("config:load"),
    save: (data) => electron.ipcRenderer.invoke("config:save", data),
    exists: () => electron.ipcRenderer.invoke("config:exists"),
    getRecentFolders: (consoleKey) => electron.ipcRenderer.invoke("config:getRecentFolders", consoleKey),
    addRecentFolder: (consoleKey, folderPath) => electron.ipcRenderer.invoke("config:addRecentFolder", consoleKey, folderPath)
  },
  server: {
    start: () => electron.ipcRenderer.invoke("server:start"),
    stop: () => electron.ipcRenderer.invoke("server:stop"),
    token: () => electron.ipcRenderer.invoke("server:token"),
    changePin: (pin) => electron.ipcRenderer.invoke("server:change-pin", pin),
    discover: () => electron.ipcRenderer.invoke("server:discover")
  },
  launcher: {
    path: () => electron.ipcRenderer.invoke("launcher:path")
  },
  dialog: {
    openFile: (options) => electron.ipcRenderer.invoke("dialog:openFile", {
      properties: ["openFile"],
      ...options
    }),
    openFolder: () => electron.ipcRenderer.invoke("dialog:openFolder")
  },
  emulator: {
    consoles: () => electron.ipcRenderer.invoke("emulator:consoles"),
    detect: (consoleKey) => electron.ipcRenderer.invoke("emulator:detect", consoleKey),
    scan: (consoleKey, emulatorOption, extraPaths) => electron.ipcRenderer.invoke("emulator:scan", { consoleKey, emulatorOption, extraPaths })
  },
  files: {
    ensureSave: (savePath) => electron.ipcRenderer.invoke("files:ensure-save", savePath),
    getSaveTime: (savePath) => electron.ipcRenderer.invoke("files:get-save-time", savePath)
  },
  game: {
    launch: (slug, command) => electron.ipcRenderer.invoke("game:launch", slug, command),
    stop: () => electron.ipcRenderer.invoke("game:stop"),
    isRunning: () => electron.ipcRenderer.invoke("game:isRunning"),
    stopExternal: () => electron.ipcRenderer.invoke("game:stop-external"),
    hasPidFile: () => electron.ipcRenderer.invoke("game:hasPidFile"),
    onExited: (cb) => {
      electron.ipcRenderer.on("game:exited", cb);
    },
    offExited: (cb) => {
      electron.ipcRenderer.removeListener("game:exited", cb);
    }
  },
  log: {
    message: (message) => electron.ipcRenderer.invoke("log:message", message)
  }
});
