// Preload (sandbox + contextIsolation): renderer'ga faqat oyna boshqaruvini beradi.
// Node/Electron API'lari renderer'ga to'g'ridan-to'g'ri berilmaydi.
const { contextBridge, ipcRenderer } = require('electron');

const ALLOWED = ['minimize', 'maximize', 'close'];

contextBridge.exposeInMainWorld('posWin', {
  send: (cmd) => {
    if (ALLOWED.includes(cmd)) ipcRenderer.send('win-' + cmd);
  },
});
