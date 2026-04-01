const { app, BrowserWindow, Menu } = require('electron');
const path = require('path');
const url = require('url');

function createWindow() {
  const mainWindow = new BrowserWindow({
    width: 1366,
    height: 768,
    minWidth: 1024,
    minHeight: 768,
    // Kiosk yoki To'liq ekran qilish uchun:
    fullscreenable: true,
    // kiosk: true, // yechimsiz to'liq ekran
    show: false, // Tayyor bo'lguncha yashirib turamiz
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false
    }
  });

  // Windows menyularini o'chirish
  Menu.setApplicationMenu(null);

  // App ishlash rejimiga qarab yuklash
  const devUrl = 'http://localhost:5173/pos-login';
  
  if (process.env.NODE_ENV === 'development') {
    mainWindow.loadURL(devUrl);
    mainWindow.webContents.openDevTools();
  } else {
    // Build qilingan frontendni yuklash
    mainWindow.loadURL(url.format({
      pathname: path.join(__dirname, '../dist/index.html'),
      protocol: 'file:',
      slashes: true,
      hash: '/pos-login' // Router ishlaydigan joy
    }));
  }

  // Oyna tayyorlanganda ko'rsatish
  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    mainWindow.maximize();
  });
}

app.whenReady().then(() => {
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
