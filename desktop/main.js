const { app, BrowserWindow, ipcMain, dialog, Menu } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const express = require('express');
const cors = require('cors');
const multer = require('multer');
const fs = require('fs');
const fsPromises = require('fs').promises;

let mainWindow;
let flaskProcess;
let expressApp;
let server;

// Create necessary directories
const createDirectories = () => {
  const dirs = ['uploads', 'temp', 'outputs', 'alignments'];
  dirs.forEach(dir => {
    const dirPath = path.join(__dirname, dir);
    if (!fs.existsSync(dirPath)) {
      fs.mkdirSync(dirPath, { recursive: true });
    }
  });
};

// Start Flask backend
const startFlaskBackend = () => {
  return new Promise((resolve, reject) => {
    const pythonPath = process.platform === 'win32' ? 'python' : 'python3';
    const flaskPath = path.join(__dirname, '..', 'backend', 'app.py');
    
    flaskProcess = spawn(pythonPath, [flaskPath], {
      cwd: path.join(__dirname, '..'),
      stdio: 'pipe'
    });

    flaskProcess.stdout.on('data', (data) => {
      console.log(`Flask: ${data}`);
      if (data.toString().includes('Running on')) {
        resolve();
      }
    });

    flaskProcess.stderr.on('data', (data) => {
      console.error(`Flask Error: ${data}`);
      reject(data);
    });

    flaskProcess.on('close', (code) => {
      console.log(`Flask process exited with code ${code}`);
    });
  });
};

// Start Express server for file serving
const startExpressServer = () => {
  expressApp = express();
  expressApp.use(cors());
  expressApp.use(express.json());
  expressApp.use(express.static(path.join(__dirname, '..', 'frontend')));
  expressApp.use('/uploads', express.static(path.join(__dirname, '..', 'uploads')));
  expressApp.use('/temp', express.static(path.join(__dirname, '..', 'temp')));

  // File upload endpoint
  const storage = multer.diskStorage({
    destination: (req, file, cb) => {
      const uploadPath = path.join(__dirname, '..', 'uploads');
      cb(null, uploadPath);
    },
    filename: (req, file, cb) => {
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
      cb(null, `${timestamp}_${file.originalname}`);
    }
  });

  const upload = multer({ 
    storage: storage,
    limits: { 
      fileSize: 100 * 1024 * 1024 // 100MB limit
    }
  });

  expressApp.post('/upload', upload.fields([
    { name: 'audio', maxCount: 1 },
    { name: 'image', maxCount: 1 }
  ]), (req, res) => {
    res.json({ 
      success: true, 
      files: req.files,
      message: 'Files uploaded successfully'
    });
  });

  server = expressApp.listen(3001, () => {
    console.log('Express server running on port 3001');
  });
};

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    },
    icon: path.join(__dirname, 'assets', 'icon.png'),
    titleBarStyle: 'default',
    show: false
  });

  // Load the frontend
  mainWindow.loadFile(path.join(__dirname, '..', 'frontend', 'index.html'));

  // Create menu
  const template = [
    {
      label: 'File',
      submenu: [
        {
          label: 'New Project',
          accelerator: 'CmdOrCtrl+N',
          click: () => {
            mainWindow.webContents.send('menu-new-project');
          }
        },
        {
          label: 'Open Audio File',
          accelerator: 'CmdOrCtrl+O',
          click: async () => {
            const result = await dialog.showOpenDialog(mainWindow, {
              properties: ['openFile'],
              filters: [
                { name: 'Audio Files', extensions: ['mp3', 'wav', 'm4a', 'flac'] }
              ]
            });
            
            if (!result.canceled) {
              mainWindow.webContents.send('menu-open-audio', result.filePaths[0]);
            }
          }
        },
        { type: 'separator' },
        {
          label: 'Export Video',
          accelerator: 'CmdOrCtrl+E',
          click: async () => {
            const result = await dialog.showSaveDialog(mainWindow, {
              filters: [
                { name: 'MP4 Video', extensions: ['mp4'] }
              ],
              defaultPath: 'lyric-video.mp4'
            });
            
            if (!result.canceled) {
              mainWindow.webContents.send('menu-export-video', result.filePath);
            }
          }
        },
        { type: 'separator' },
        {
          label: 'Exit',
          accelerator: process.platform === 'darwin' ? 'Cmd+Q' : 'Ctrl+Q',
          click: () => {
            app.quit();
          }
        }
      ]
    },
    {
      label: 'Edit',
      submenu: [
        { role: 'undo' },
        { role: 'redo' },
        { type: 'separator' },
        { role: 'cut' },
        { role: 'copy' },
        { role: 'paste' }
      ]
    },
    {
      label: 'View',
      submenu: [
        { role: 'reload' },
        { role: 'forceReload' },
        { role: 'toggleDevTools' },
        { type: 'separator' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'togglefullscreen' }
      ]
    },
    {
      label: 'Help',
      submenu: [
        {
          label: 'About',
          click: () => {
            dialog.showMessageBox(mainWindow, {
              type: 'info',
              title: 'About Dorian Lyrics Maker',
              message: 'Dorian Lyrics Maker v1.0.0',
              detail: 'A desktop application for creating synchronized lyric videos with per-word highlighting.'
            });
          }
        }
      ]
    }
  ];

  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    
    // Maximize window on larger screens
    if (process.platform === 'win32' || process.platform === 'linux') {
      mainWindow.maximize();
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// IPC handlers
ipcMain.handle('get-app-version', () => {
  return app.getVersion();
});

ipcMain.handle('show-save-dialog', async (event, options) => {
  const result = await dialog.showSaveDialog(mainWindow, options);
  return result;
});

ipcMain.handle('show-open-dialog', async (event, options) => {
  const result = await dialog.showOpenDialog(mainWindow, options);
  return result;
});

ipcMain.handle('get-path', (event, name) => {
  return app.getPath(name);
});

// App event handlers
app.whenReady().then(async () => {
  createDirectories();
  
  try {
    await startFlaskBackend();
    startExpressServer();
    createWindow();
  } catch (error) {
    console.error('Failed to start backend:', error);
    dialog.showErrorBox('Startup Error', 'Failed to start Flask backend. Please ensure Python and required packages are installed.');
    app.quit();
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  // Cleanup
  if (flaskProcess) {
    flaskProcess.kill();
  }
  if (server) {
    server.close();
  }
});

// Handle uncaught exceptions
process.on('uncaughtException', (error) => {
  console.error('Uncaught Exception:', error);
  dialog.showErrorBox('Application Error', error.message);
});

process.on('unhandledRejection', (reason, promise) => {
  console.error('Unhandled Rejection at:', promise, 'reason:', reason);
});
