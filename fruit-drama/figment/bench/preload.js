const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('bench', { report: (r) => ipcRenderer.send('bench-result', r) });
