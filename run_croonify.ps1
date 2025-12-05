# Dorian Lyrics Maker v1 - One-Click Launcher (Windows PowerShell)
# This script sets up a Python virtualenv, installs dependencies (tolerates aeneas failure),
# checks for FFmpeg, starts backend and frontend servers, and opens the browser.

[CmdletBinding()] param()
$ErrorActionPreference = 'Continue'

function Write-Info($msg) { Write-Host $msg -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host $msg -ForegroundColor Green }
function Write-Warn($msg) { Write-Warning $msg }
function Fail($msg) { Write-Host $msg -ForegroundColor Red; exit 1 }

# Resolve project root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir
Write-Info "Project root: $ScriptDir"

# Detect Python launcher
function Get-PythonLauncher {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { return 'py -3' }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) { return 'python' }
    Fail 'Python 3.x not found. Please install Python and retry.'
}
$PythonLauncher = Get-PythonLauncher
Write-Info "Using Python launcher: $PythonLauncher"

# Create venv if missing
$VenvPython = Join-Path $ScriptDir 'venv/Scripts/python.exe'
$VenvPip = Join-Path $ScriptDir 'venv/Scripts/pip.exe'
if (!(Test-Path $VenvPython)) {
    Write-Info 'Creating virtual environment (venv)...'
    if ($PythonLauncher -eq 'py -3') {
        & py -3 -m venv venv
    } else {
        & python -m venv venv
    }
}
if (!(Test-Path $VenvPython)) { Fail 'Failed to create virtual environment.' }

# Upgrade pip
Write-Info 'Upgrading pip...'
& $VenvPython -m pip install --upgrade pip

# Install dependencies from requirements.txt, tolerating failures (e.g., aeneas)
$ReqPath = Join-Path $ScriptDir 'requirements.txt'
if (Test-Path $ReqPath) {
    Write-Info 'Installing dependencies from requirements.txt (will continue on failures)...'
    $pkgs = Get-Content $ReqPath | Where-Object { $_ -and $_ -notmatch '^\s*#' }
    foreach ($pkg in $pkgs) {
        Write-Info "Installing $pkg ..."
        & $VenvPython -m pip install $pkg
        if ($LASTEXITCODE -ne 0) { Write-Warn "Failed to install $pkg; continuing." }
    }
} else {
    Write-Info 'requirements.txt not found; installing core dependencies...'
    & $VenvPython -m pip install flask werkzeug pydub numpy moviepy pillow requests
}

# Check FFmpeg availability
$ffmpegCmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
if (-not $ffmpegCmd) {
    Write-Warn 'FFmpeg not found in PATH. Audio/video processing may fail.'
    Write-Info 'Install options: winget install ffmpeg  OR  choco install ffmpeg  OR  download from https://www.gyan.dev/ffmpeg/builds/'
}

# Performance tuning: allow backend to use all CPU cores and faster encoder settings
if (-not $env:FFMPEG_THREADS) { $env:FFMPEG_THREADS = '0' }
if (-not $env:FFMPEG_PRESET)  { $env:FFMPEG_PRESET = 'ultrafast' }
if (-not $env:FFMPEG_ENCODER) { $env:FFMPEG_ENCODER = 'h264_amf' }
if (-not $env:FFMPEG_TUNE)    { $env:FFMPEG_TUNE    = 'zerolatency' }
if (-not $env:CROONIFY_WIDTH) { $env:CROONIFY_WIDTH = '1280' }
if (-not $env:CROONIFY_HEIGHT){ $env:CROONIFY_HEIGHT= '720' }

# Start backend server
Write-Info 'Starting backend (Flask) on http://localhost:5000 ...'
$env:PYTHONPATH = "$ScriptDir" + ';' + ($env:PYTHONPATH)
$env:CROONIFY_BACKEND_PORT = '5000'
$env:CROONIFY_FRONTEND_PORT = '5500'
try {
    $backend = Start-Process -FilePath $VenvPython -ArgumentList '-m','backend.app' -WorkingDirectory $ScriptDir -WindowStyle Minimized -PassThru
} catch {
    Write-Warn 'Module start failed, falling back to backend/app.py'
    $backend = Start-Process -FilePath $VenvPython -ArgumentList (Join-Path $ScriptDir 'backend/app.py') -WorkingDirectory (Join-Path $ScriptDir 'backend') -WindowStyle Minimized -PassThru
}

# Start frontend static server (prefer frontend/, fallback to desktop/frontend)
$FrontendDir = Join-Path $ScriptDir 'frontend'
if (!(Test-Path $FrontendDir)) {
    $alt = Join-Path $ScriptDir 'desktop/frontend'
    if (Test-Path $alt) { $FrontendDir = $alt } else { Fail "Frontend directory not found: $FrontendDir" }
}
Write-Info 'Starting frontend at http://localhost:5500 ...'
$frontend = Start-Process -FilePath $VenvPython -ArgumentList '-m','http.server','5500' -WorkingDirectory $FrontendDir -WindowStyle Minimized -PassThru

# Wait briefly and print URLs
Start-Sleep -Seconds 2
Write-Ok 'Dorian Lyrics Maker v1 is ready.'
Write-Ok 'Frontend:  http://localhost:5500/'
Write-Ok 'Backend:   http://localhost:5000/'

# Open browser
try { Start-Process 'http://localhost:5500/' } catch { Write-Warn 'Failed to open browser automatically. Please open http://localhost:5500/ manually.' }

Write-Info 'To stop, close the two minimized server windows that were opened.'