"use strict";
const electron = require("electron");
electron.contextBridge.exposeInMainWorld("emusync", {
  config: {
    load: () => electron.ipcRenderer.invoke("config:load"),
    save: (data) => electron.ipcRenderer.invoke("config:save", data),
    exists: () => electron.ipcRenderer.invoke("config:exists")
  },
  server: {
    start: () => electron.ipcRenderer.invoke("server:start"),
    stop: () => electron.ipcRenderer.invoke("server:stop")
  },
  dialog: {
    openFile: (options) => electron.ipcRenderer.invoke("dialog:openFile", {
      properties: ["openFile"],
      ...options
    })
  }
});
