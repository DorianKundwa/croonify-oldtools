const { contextBridge, ipcRenderer } = require('electron');

// Expose protected methods that allow the renderer process to use
// the ipcRenderer without exposing the entire object
contextBridge.exposeInMainWorld('electronAPI', {
  // App info
  getAppVersion: () => ipcRenderer.invoke('get-app-version'),
  
  // Dialog operations
  showSaveDialog: (options) => ipcRenderer.invoke('show-save-dialog', options),
  showOpenDialog: (options) => ipcRenderer.invoke('show-open-dialog', options),
  
  // Path operations
  getPath: (name) => ipcRenderer.invoke('get-path', name),
  
  // Menu event listeners
  onMenuNewProject: (callback) => ipcRenderer.on('menu-new-project', callback),
  onMenuOpenAudio: (callback) => ipcRenderer.on('menu-open-audio', callback),
  onMenuExportVideo: (callback) => ipcRenderer.on('menu-export-video', callback),
  
  // Remove listeners
  removeAllListeners: (channel) => ipcRenderer.removeAllListeners(channel)
});

// Add desktop-specific styles
document.addEventListener('DOMContentLoaded', () => {
  // Add desktop-specific CSS
  const style = document.createElement('style');
  style.textContent = `
    /* Desktop-specific styles */
    .desktop-title-bar {
      -webkit-app-region: drag;
      height: 30px;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      display: flex;
      align-items: center;
      padding: 0 15px;
      color: white;
      font-weight: 500;
      font-size: 14px;
    }
    
    .desktop-content {
      -webkit-app-region: no-drag;
      height: calc(100vh - 30px);
      overflow: hidden;
    }
    
    /* Enhanced scrollbar for desktop */
    ::-webkit-scrollbar {
      width: 8px;
    }
    
    ::-webkit-scrollbar-track {
      background: #f1f1f1;
      border-radius: 4px;
    }
    
    ::-webkit-scrollbar-thumb {
      background: #c1c1c1;
      border-radius: 4px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
      background: #a8a8a8;
    }
    
    /* Desktop-specific button enhancements */
    .desktop-button {
      transition: all 0.2s ease;
      border: none;
      cursor: pointer;
    }
    
    .desktop-button:hover {
      transform: translateY(-1px);
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    }
    
    .desktop-button:active {
      transform: translateY(0);
    }
    
    /* File input enhancements for desktop */
    input[type="file"] {
      cursor: pointer;
    }
    
    input[type="file"]:hover {
      background-color: rgba(102, 126, 234, 0.05);
    }
  `;
  document.head.appendChild(style);
  
  // Add title bar for desktop
  const titleBar = document.createElement('div');
  titleBar.className = 'desktop-title-bar';
  titleBar.textContent = 'Dorian Lyrics Maker';
  
  // Move original content into desktop container
  const originalContent = document.body.innerHTML;
  document.body.innerHTML = '';
  
  const desktopContainer = document.createElement('div');
  desktopContainer.className = 'desktop-content';
  desktopContainer.innerHTML = originalContent;
  
  document.body.appendChild(titleBar);
  document.body.appendChild(desktopContainer);
  
  // Apply desktop enhancements to existing elements
  setTimeout(() => {
    // Enhance buttons
    const buttons = desktopContainer.querySelectorAll('button');
    buttons.forEach(button => {
      button.classList.add('desktop-button');
    });
    
    // Enhance file inputs
    const fileInputs = desktopContainer.querySelectorAll('input[type="file"]');
    fileInputs.forEach(input => {
      input.classList.add('desktop-file-input');
    });
    
    // Add desktop-specific functionality
    enhanceForDesktop();
  }, 100);
});

// Desktop-specific enhancements
function enhanceForDesktop() {
  // Add keyboard shortcuts
  document.addEventListener('keydown', (e) => {
    if (e.ctrlKey || e.metaKey) {
      switch (e.key) {
        case 'n':
          e.preventDefault();
          window.electronAPI.onMenuNewProject(() => {});
          break;
        case 'o':
          e.preventDefault();
          handleOpenAudio();
          break;
        case 'e':
          e.preventDefault();
          handleExportVideo();
          break;
      }
    }
  });
  
  // Add drag and drop support
  document.addEventListener('dragover', (e) => {
    e.preventDefault();
    e.stopPropagation();
  });
  
  document.addEventListener('drop', async (e) => {
    e.preventDefault();
    e.stopPropagation();
    
    const files = Array.from(e.dataTransfer.files);
    const audioFiles = files.filter(file => 
      file.type.startsWith('audio/') || 
      file.name.match(/\.(mp3|wav|m4a|flac)$/i)
    );
    const imageFiles = files.filter(file => 
      file.type.startsWith('image/') || 
      file.name.match(/\.(jpg|jpeg|png|gif)$/i)
    );
    
    if (audioFiles.length > 0) {
      await handleDroppedAudio(audioFiles[0]);
    }
    
    if (imageFiles.length > 0) {
      await handleDroppedImage(imageFiles[0]);
    }
  });
}

// Handle opening audio files
async function handleOpenAudio() {
  const result = await window.electronAPI.showOpenDialog({
    properties: ['openFile'],
    filters: [
      { name: 'Audio Files', extensions: ['mp3', 'wav', 'm4a', 'flac'] }
    ]
  });
  
  if (!result.canceled && result.filePaths.length > 0) {
    const filePath = result.filePaths[0];
    // Trigger audio file loading in the main app
    const audioInput = document.querySelector('input[type="file"]');
    if (audioInput) {
      // Create a File object from the path and trigger the change event
      // This would need to be implemented based on your specific app structure
      console.log('Opening audio file:', filePath);
    }
  }
}

// Handle exporting video
async function handleExportVideo() {
  const result = await window.electronAPI.showSaveDialog({
    filters: [
      { name: 'MP4 Video', extensions: ['mp4'] }
    ],
    defaultPath: 'lyric-video.mp4'
  });
  
  if (!result.canceled) {
    const filePath = result.filePath;
    // Trigger video export in the main app
    console.log('Exporting video to:', filePath);
  }
}

// Handle dropped audio files
async function handleDroppedAudio(file) {
  console.log('Dropped audio file:', file.name);
  // Process the dropped audio file
  // This would need to be integrated with your existing file handling logic
}

// Handle dropped image files
async function handleDroppedImage(file) {
  console.log('Dropped image file:', file.name);
  // Process the dropped image file
  // This would need to be integrated with your existing file handling logic
}