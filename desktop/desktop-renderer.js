// Desktop Renderer Process Script
// Enhanced version of the web frontend for desktop use

let currentAudioFile = null;
let currentLyrics = '';
let audioContext = null;
let audioBuffer = null;
let alignmentData = null;
let isPlaying = false;
let startTime = 0;
let pauseTime = 0;
let animationId = null;
let jobId = null;

// Initialize desktop app
document.addEventListener('DOMContentLoaded', () => {
    initializeEventListeners();
    setupDragAndDrop();
    checkElectronAPI();
});

function checkElectronAPI() {
    if (window.electronAPI) {
        console.log('Desktop API available');
        setupDesktopFeatures();
    } else {
        console.log('Running in web mode');
    }
}

function setupDesktopFeatures() {
    // Listen for menu events from main process
    window.electronAPI.onMenuNewProject(() => {
        resetProject();
    });
    
    window.electronAPI.onMenuOpenAudio((event, filePath) => {
        handleFileFromPath(filePath, 'audio');
    });
    
    window.electronAPI.onMenuExportVideo((event, filePath) => {
        exportVideoToPath(filePath);
    });
    
    // Add keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if (e.ctrlKey || e.metaKey) {
            switch (e.key) {
                case 'n':
                    e.preventDefault();
                    resetProject();
                    break;
                case 'o':
                    e.preventDefault();
                    openFileDialog('audio');
                    break;
                case 's':
                    e.preventDefault();
                    saveProject();
                    break;
            }
        }
    });
}

function initializeEventListeners() {
    // File input listeners
    const audioFileInput = document.getElementById('audioFile');
    
    const lyricsInput = document.getElementById('lyricsInput');
    const generateBtn = document.getElementById('generateBtn');
    const previewBtn = document.getElementById('previewBtn');
    
    audioFileInput.addEventListener('change', (e) => handleFileSelect(e, 'audio'));
    
    lyricsInput.addEventListener('input', (e) => {
        currentLyrics = e.target.value;
        updatePreview();
    });
    
    generateBtn.addEventListener('click', generateVideo);
    previewBtn.addEventListener('click', togglePreview);
    
    // Video controls
    const videoPlayer = document.getElementById('videoPlayer');
    const playBtn = document.getElementById('playBtn');
    const pauseBtn = document.getElementById('pauseBtn');
    const stopBtn = document.getElementById('stopBtn');
    
    playBtn.addEventListener('click', () => playAudio());
    pauseBtn.addEventListener('click', () => pauseAudio());
    stopBtn.addEventListener('click', () => stopAudio());
    
    if (videoPlayer) {
        videoPlayer.addEventListener('timeupdate', updateLyricsDisplay);
        videoPlayer.addEventListener('loadedmetadata', () => {
            updateTimeDisplay();
        });
    }
}

function setupDragAndDrop() {
    const audioDropArea = document.getElementById('audioDropArea');
    
    [audioDropArea].forEach(area => {
        area.addEventListener('dragover', (e) => {
            e.preventDefault();
            area.classList.add('dragover');
        });
        
        area.addEventListener('dragleave', () => {
            area.classList.remove('dragover');
        });
        
        area.addEventListener('drop', (e) => {
            e.preventDefault();
            area.classList.remove('dragover');
            
            const files = Array.from(e.dataTransfer.files);
            const type = 'audio';
            const validFiles = files.filter(file => validateFile(file, type));
            
            if (validFiles.length > 0) {
                handleFile(validFiles[0], type);
            }
        });
    });
}

function validateFile(file, type) {
    const validTypes = {
        audio: ['audio/mpeg', 'audio/wav', 'audio/mp4', 'audio/flac', 'audio/x-wav']
    };
    
    const extensions = {
        audio: ['mp3', 'wav', 'm4a', 'flac']
    };
    
    const fileExtension = file.name.split('.').pop().toLowerCase();
    const isValidType = validTypes.audio.includes(file.type) || extensions.audio.includes(fileExtension);
    
    if (!isValidType) {
        showMessage(`Invalid ${type} file format`, 'error');
        return false;
    }
    
    const maxSize = 100 * 1024 * 1024; // 100MB for audio
    if (file.size > maxSize) {
        showMessage(`${type} file too large. Maximum size: ${maxSize / (1024 * 1024)}MB`, 'error');
        return false;
    }
    
    return true;
}

function handleFileSelect(event, type) {
    const file = event.target.files[0];
    if (file) {
        handleFile(file, type);
    }
}

function handleFile(file, type) {
    if (!validateFile(file, type)) return;
    
    if (type === 'audio') {
        currentAudioFile = file;
        document.getElementById('audioFileInfo').textContent = `${file.name} (${formatFileSize(file.size)})`;
        loadAudioFile(file);
    }
    
    updatePreview();
    showMessage(`${type} file loaded successfully`, 'success');
}

function handleFileFromPath(filePath, type) {
    // Handle file opened from system dialog
    fetch(filePath)
        .then(response => response.blob())
        .then(blob => {
            const file = new File([blob], filePath.split('\\').pop() || filePath.split('/').pop(), {
                type: type === 'audio' ? 'audio/mpeg' : 'image/jpeg'
            });
            handleFile(file, type);
        })
        .catch(error => {
            showMessage(`Error loading file: ${error.message}`, 'error');
        });
}

function loadAudioFile(file) {
    const reader = new FileReader();
    reader.onload = async (e) => {
        try {
            if (!audioContext) {
                audioContext = new (window.AudioContext || window.webkitAudioContext)();
            }
            
            const arrayBuffer = e.target.result;
            audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
            
            // Set up video player with audio
            const videoPlayer = document.getElementById('videoPlayer');
            const audioUrl = URL.createObjectURL(file);
            videoPlayer.src = audioUrl;
            
            showMessage('Audio loaded successfully', 'success');
        } catch (error) {
            showMessage(`Error loading audio: ${error.message}`, 'error');
        }
    };
    reader.readAsArrayBuffer(file);
}

async function generateVideo() {
    if (!currentAudioFile || !currentLyrics.trim()) {
        showMessage('Please provide both audio file and lyrics', 'error');
        return;
    }
    
    const formData = new FormData();
    formData.append('audio', currentAudioFile);
    
    formData.append('lyrics', currentLyrics);
    
    showProgress(0, 'Uploading files...');
    
    try {
        // Upload files
        const uploadResponse = await fetch('http://localhost:5000/upload', {
            method: 'POST',
            body: formData
        });
        
        if (!uploadResponse.ok) {
            throw new Error('Upload failed');
        }
        
        const uploadData = await uploadResponse.json();
        jobId = uploadData.job_id;
        
        // Start generation
        showProgress(10, 'Generating synchronized lyrics...');
        const generateResponse = await fetch('http://localhost:5000/generate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ job_id: jobId })
        });
        
        if (!generateResponse.ok) {
            throw new Error('Generation failed');
        }
        
        // Poll for status
        await pollJobStatus();
        
    } catch (error) {
        showMessage(`Error: ${error.message}`, 'error');
        hideProgress();
    }
}

async function pollJobStatus() {
    const checkStatus = async () => {
        try {
            const response = await fetch(`http://localhost:5000/status/${jobId}`);
            const data = await response.json();
            
            if (data.status === 'completed') {
                showProgress(100, 'Video generated successfully!');
                alignmentData = data.alignment;
                
                // Load the generated video
                const videoPlayer = document.getElementById('videoPlayer');
                videoPlayer.src = `http://localhost:5000/download/${jobId}`;
                videoPlayer.style.display = 'block';
                document.getElementById('videoControls').style.display = 'flex';
                document.getElementById('placeholder').style.display = 'none';
                
                showMessage('Video generated successfully!', 'success');
                hideProgress();
                
            } else if (data.status === 'processing') {
                const progress = data.progress || 50;
                showProgress(progress, 'Processing video...');
                setTimeout(checkStatus, 2000);
                
            } else if (data.status === 'error') {
                throw new Error(data.message || 'Processing failed');
                
            } else {
                setTimeout(checkStatus, 2000);
            }
            
        } catch (error) {
            showMessage(`Status check failed: ${error.message}`, 'error');
            hideProgress();
        }
    };
    
    checkStatus();
}

function togglePreview() {
    const videoPlayer = document.getElementById('videoPlayer');
    const previewBtn = document.getElementById('previewBtn');
    
    if (currentAudioFile && currentLyrics) {
        if (videoPlayer.style.display === 'none') {
            videoPlayer.style.display = 'block';
            document.getElementById('videoControls').style.display = 'flex';
            document.getElementById('placeholder').style.display = 'none';
            previewBtn.textContent = '👁️ Hide Preview';
        } else {
            videoPlayer.style.display = 'none';
            document.getElementById('videoControls').style.display = 'none';
            document.getElementById('placeholder').style.display = 'block';
            previewBtn.textContent = '👁️ Preview';
        }
    } else {
        showMessage('Please load audio and lyrics first', 'error');
    }
}

function updatePreview() {
    if (currentLyrics && currentAudioFile) {
        // Simple preview without alignment
        const overlay = document.getElementById('lyricsOverlay');
        overlay.innerHTML = currentLyrics.replace(/\n/g, '<br>');
        overlay.style.display = 'block';
    }
}

function playAudio() {
    const videoPlayer = document.getElementById('videoPlayer');
    if (videoPlayer.src) {
        videoPlayer.play();
        isPlaying = true;
        startTime = Date.now() - pauseTime;
        updateAnimation();
    }
}

function pauseAudio() {
    const videoPlayer = document.getElementById('videoPlayer');
    videoPlayer.pause();
    isPlaying = false;
    pauseTime = Date.now() - startTime;
    if (animationId) {
        cancelAnimationFrame(animationId);
    }
}

function stopAudio() {
    const videoPlayer = document.getElementById('videoPlayer');
    videoPlayer.pause();
    videoPlayer.currentTime = 0;
    isPlaying = false;
    pauseTime = 0;
    if (animationId) {
        cancelAnimationFrame(animationId);
    }
    updateLyricsDisplay();
}

function updateAnimation() {
    if (!isPlaying) return;
    
    updateLyricsDisplay();
    animationId = requestAnimationFrame(updateAnimation);
}

function updateLyricsDisplay() {
    const videoPlayer = document.getElementById('videoPlayer');
    const overlay = document.getElementById('lyricsOverlay');
    const currentTime = videoPlayer.currentTime;
    
    if (alignmentData && alignmentData.fragments) {
        const currentFragment = alignmentData.fragments.find(fragment => 
            currentTime >= parseFloat(fragment.begin) && currentTime <= parseFloat(fragment.end)
        );
        
        if (currentFragment) {
            const words = currentFragment.lines[0].split(' ');
            const fragmentStart = parseFloat(currentFragment.begin);
            const fragmentDuration = parseFloat(currentFragment.end) - fragmentStart;
            const wordDuration = fragmentDuration / words.length;
            const wordIndex = Math.floor((currentTime - fragmentStart) / wordDuration);
            
            const highlightedWords = words.map((word, index) => 
                `<span class="word ${index === wordIndex ? 'active' : ''}">${word}</span>`
            ).join(' ');
            
            overlay.innerHTML = highlightedWords;
        }
    }
    
    updateTimeDisplay();
}

function updateTimeDisplay() {
    const videoPlayer = document.getElementById('videoPlayer');
    const timeDisplay = document.getElementById('timeDisplay');
    const current = formatTime(videoPlayer.currentTime);
    const total = formatTime(videoPlayer.duration || 0);
    timeDisplay.textContent = `${current} / ${total}`;
}

function formatTime(seconds) {
    if (isNaN(seconds)) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function showProgress(percent, message) {
    const progressSection = document.getElementById('progressSection');
    const progressFill = document.getElementById('progressFill');
    const statusText = document.getElementById('statusText');
    
    progressSection.style.display = 'block';
    progressFill.style.width = `${percent}%`;
    statusText.textContent = message;
}

function hideProgress() {
    setTimeout(() => {
        document.getElementById('progressSection').style.display = 'none';
    }, 1000);
}

function showMessage(message, type) {
    const messagesDiv = document.getElementById('messages');
    const messageDiv = document.createElement('div');
    messageDiv.className = type === 'error' ? 'error-message' : 'success-message';
    messageDiv.textContent = message;
    
    messagesDiv.appendChild(messageDiv);
    
    setTimeout(() => {
        messageDiv.remove();
    }, 5000);
}

function resetProject() {
    currentAudioFile = null;
    currentLyrics = '';
    alignmentData = null;
    jobId = null;
    
    document.getElementById('audioFile').value = '';
    document.getElementById('lyricsInput').value = '';
    document.getElementById('audioFileInfo').textContent = 'No file selected';
    
    const videoPlayer = document.getElementById('videoPlayer');
    videoPlayer.src = '';
    videoPlayer.style.display = 'none';
    document.getElementById('videoControls').style.display = 'none';
    document.getElementById('placeholder').style.display = 'block';
    document.getElementById('lyricsOverlay').style.display = 'none';
    
    showMessage('Project reset successfully', 'success');
}

function openFileDialog(type) {
    if (window.electronAPI) {
        window.electronAPI.showOpenDialog({
            properties: ['openFile'],
            filters: [{
                name: type === 'audio' ? 'Audio Files' : 'Image Files',
                extensions: type === 'audio' ? ['mp3', 'wav', 'm4a', 'flac'] : ['jpg', 'jpeg', 'png', 'gif']
            }]
        }).then(result => {
            if (!result.canceled && result.filePaths.length > 0) {
                handleFileFromPath(result.filePaths[0], type);
            }
        });
    } else {
        // Fallback to native file input
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = type === 'audio' ? 'audio/*' : 'image/*';
        input.onchange = (e) => handleFileSelect(e, type);
        input.click();
    }
}

function saveProject() {
    const projectData = {
        audioFile: currentAudioFile ? {
            name: currentAudioFile.name,
            size: currentAudioFile.size,
            type: currentAudioFile.type
        } : null,
        
        lyrics: currentLyrics,
        alignmentData: alignmentData,
        timestamp: new Date().toISOString()
    };
    
    if (window.electronAPI) {
        window.electronAPI.showSaveDialog({
            filters: [{
                name: 'Dorian Project',
                extensions: ['dorian']
            }],
            defaultPath: 'project.dorian'
        }).then(result => {
            if (!result.canceled) {
                const dataStr = JSON.stringify(projectData, null, 2);
                const blob = new Blob([dataStr], { type: 'application/json' });
                const url = URL.createObjectURL(blob);
                
                const a = document.createElement('a');
                a.href = url;
                a.download = result.filePath;
                a.click();
                
                URL.revokeObjectURL(url);
                showMessage('Project saved successfully', 'success');
            }
        });
    }
}

function exportVideoToPath(filePath) {
    if (jobId) {
        // Download the generated video
        fetch(`http://localhost:5000/download/${jobId}`)
            .then(response => response.blob())
            .then(blob => {
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = filePath;
                a.click();
                URL.revokeObjectURL(url);
                showMessage('Video exported successfully', 'success');
            })
            .catch(error => {
                showMessage(`Export failed: ${error.message}`, 'error');
            });
    } else {
        showMessage('No video generated yet', 'error');
    }
}