# Croonify — AI Lyric Video Generator

> **Turn any song into a fully synchronized lyric video in minutes.**  
> Upload audio or video + lyrics → AI aligns every word → 1080p HD video with per-word highlighting, background art, and an optional branded outro.

---

## Table of Contents

1. [Features](#features)
2. [Architecture Overview](#architecture-overview)
3. [Tech Stack](#tech-stack)
4. [Quick Start](#quick-start)
5. [File Structure](#file-structure)
6. [Backend Modules](#backend-modules)
7. [API Reference](#api-reference)
8. [Configuration](#configuration)
9. [Lyric Editor](#lyric-editor)
10. [Supported Formats](#supported-formats)
11. [Performance Tuning](#performance-tuning)
12. [Testing](#testing)
13. [Deployment](#deployment)

---

## Features

### Core Pipeline
- **AI Lyric Alignment** — 5-layer hybrid engine (WhisperX + fuzzy DP + phonetic matching + cubic-spline interpolation + QA pass) achieves high word-level accuracy across 20+ languages
- **Stem Separation** — Demucs → Spleeter → FFmpeg mid/side fallback chain; auto-selects best available engine
- **1080p HD Video Output** — 1920×1080 @ 24 fps; hardware encoder support (h264_amf, h264_nvenc, libx264)
- **Per-Word Highlighting** — live word-by-word glow effect in the browser video preview
- **Real-time Lyrics Overlay** — Web Audio API–driven overlay synced to video playback position

### Input Support
- **Audio**: MP3, WAV, M4A, AAC, FLAC, OGG, WMA, AIFF, OPUS, MP4, WEBM (up to 100 MB)
- **Video**: MP4, MOV, AVI, MKV, WEBM (up to 500 MB) — lyrics composited over the original video via screen-blend FFmpeg filter
- **Lyrics**: Plain text file (`.txt`) or LRC file (`.lrc`) or typed directly in the browser (up to 1 MB)
- **Background**: JPG / PNG image (up to 30 MB)
- **Outro**: Any audio format or video file appended to the end of the lyric section

### Lyric Editor (Post-render)
- **Visual Timeline** — drag lyric segments left/right to adjust start/end timestamps
- **Y-Position Handle** — drag lines vertically to fix subtitle position
- **Undo/Redo** — 50-step history stack (Ctrl+Z / Ctrl+Y)
- **Auto-save** — debounced 4-second auto-save after every edit
- **Re-render** — apply corrections without re-running alignment or stem separation
- **Persistent sessions** — editor state survives server restarts (job stubs saved to `alignments/_jobs_store.json`)

### Output Variants
- **Main lyric video** — vocals track + lyrics on background (image or color)
- **Instrumental variant** — same background, instrumental stem, same lyric timing
- **Outro segment** — custom audio or video appended with fade-in/fade-out text overlay
- **Thumbnail** — auto-generated 1920×1080 PNG with title + artist text overlay
- **LRC & SRT** — subtitle files exported alongside the video

---

## Architecture Overview

```
Browser (index.html)
    │  POST /upload      ←── audio/video, lyrics, background, outro
    │  POST /generate    ←── job config JSON
    │  GET  /status/:id  ←── SSE-style polling (2 s interval)
    │  PATCH /alignment/:id  ←── corrected alignment from Lyric Editor
    │  POST /rerender/:id    ←── lightweight re-render (skip alignment)
    ▼
Flask Backend (app.py)
    ├── audio_utils.py   ── normalize → stem-separate → cross-corr offset
    ├── alignment_hybrid.py  ── 5-layer hybrid aligner (primary)
    ├── alignment_whisperx.py ── WhisperX word-level timestamps
    ├── alignment_aeneas.py  ── Aeneas DTW fallback
    ├── video_builder.py ── MoviePy text clips + FFmpeg encode
    └── config.py        ── env-driven paths & FFmpeg knobs

Persistent Storage
    ├── uploads/         ── uploaded raw files
    ├── alignments/      ── alignment JSON files + _jobs_store.json
    ├── outputs/         ── rendered MP4s, thumbnails, LRC, SRT
    ├── assets/fonts/    ── custom TTF/OTF fonts
    └── logs/            ── server logs
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | Flask 2.0 (Python) |
| Frontend | Vanilla HTML5 / CSS3 / ES2020 (no framework) |
| AI speech recognition | WhisperX (OpenAI Whisper + word-level timestamps) |
| Lyric alignment | Custom 5-layer hybrid engine + Aeneas DTW |
| Stem separation | Demucs / Spleeter / FFmpeg (auto cascade) |
| Audio processing | pydub, librosa, scipy, numpy |
| Fuzzy matching | rapidfuzz (Levenshtein), jellyfish (Metaphone) |
| Video rendering | MoviePy + PIL/Pillow |
| Video encoding | FFmpeg (libx264 / h264_amf / h264_nvenc) |
| Deep learning | PyTorch ≥ 2.8, torchaudio ≥ 2.8, transformers 4.46 |
| Fonts | PIL TrueType; falls back to Windows system fonts |

---

## Quick Start

### Prerequisites

- Python 3.9–3.12
- [FFmpeg](https://www.gyan.dev/ffmpeg/builds/) installed and on `PATH`
- CUDA GPU recommended for WhisperX (CPU fallback works but is slow)

### One-click launcher (Windows)

```powershell
.\run_croonify.ps1
```

This script:
1. Creates a Python venv if missing
2. Installs all dependencies from `requirements.txt`
3. Starts the Flask backend on a free port
4. Starts a static HTTP server for the frontend
5. Opens the browser automatically

### Manual setup

```bash
# 1. Create and activate venv
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/macOS

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start the backend
python -m backend.app

# 4. Serve the frontend (separate terminal)
cd frontend
python -m http.server 8080

# 5. Open http://localhost:8080
```

> **IDE Python Interpreter**: Point your IDE to `.\venv\Scripts\python.exe` to resolve Flask/werkzeug import warnings. The system Python does not have these packages.

---

## File Structure

```
croonify-oldtools-clean-main/
├── backend/
│   ├── __init__.py
│   ├── app.py                  # Flask API — routes, job management, FFmpeg compositing
│   ├── config.py               # Paths, FFmpeg knobs, outro config (all env-overridable)
│   ├── audio_utils.py          # WAV conversion, normalization, stem sep, pitch/onset detection
│   ├── alignment_hybrid.py     # 5-layer hybrid alignment engine (primary)
│   ├── alignment_whisperx.py   # WhisperX word-level alignment
│   ├── alignment_aeneas.py     # Aeneas DTW alignment (fallback)
│   ├── video_builder.py        # MoviePy lyric video builder + thumbnail generator
│   └── lyrics_parser.py        # LRC / plain-text lyric parser
│
├── frontend/
│   ├── index.html              # Single-page application (upload → generate → preview)
│   ├── config.js               # Auto-generated: window.BACKEND_URL (set by launcher)
│   ├── lyric_editor.js         # Editor state, undo/redo, helpers
│   ├── lyric_editor_actions.js # Save, re-render, reset, auto-save
│   ├── lyric_editor_table.js   # Editable timing table UI
│   └── lyric_editor_timeline.js # Visual drag timeline canvas
│
├── scripts/
│   ├── test_app_e2e.py         # End-to-end backend API test
│   ├── test_alignment.py       # Quick alignment smoke test
│   ├── analyze_alignment.py    # Alignment quality analysis tool
│   ├── preview_alignment.py    # Print alignment JSON in human-readable form
│   ├── e2e_generate_poll.py    # Generate + poll until done (CLI)
│   ├── diagnose_46s.py         # Diagnose timing offset issues
│   ├── test_f16.py             # Test float16 WhisperX inference
│   ├── test_inst_outro_unit.py # Unit tests for instrumental outro rendering
│   ├── launch_croonify.ps1     # Alternate launcher script
│   └── run_pipeline.ps1        # Run full pipeline from PowerShell
│
├── tests/
│   ├── test_pipeline.py        # Full pipeline integration tests
│   ├── test_hybrid_align.py    # Hybrid aligner unit tests (17 KB)
│   ├── test_lyrics.py          # Lyrics parser unit tests
│   └── sample_lyrics.txt       # Sample lyrics for testing
│
├── assets/fonts/               # Custom TTF/OTF fonts (drop files here)
├── uploads/                    # Uploaded raw files (auto-created)
├── alignments/                 # Alignment JSON + _jobs_store.json (auto-created)
├── outputs/                    # Rendered videos + thumbnails (auto-created)
├── logs/                       # Server logs (auto-created)
├── requirements.txt
├── run_croonify.ps1            # One-click Windows launcher
├── vercel.json                 # Vercel deployment config
└── README.md
```

---

## Backend Modules

### `app.py` — Flask API Server
Central orchestrator. Handles:
- File upload, validation, and storage
- Job creation and background thread management (`jobs` dict + `_jobs_store.json` persistence)
- FFmpeg screen-blend compositing for video-mode (white-on-black lyric overlay)
- Outro segment rendering and concatenation (audio outro or video outro)
- Instrumental variant rendering in parallel thread
- Lyric editor endpoints (`PATCH /alignment`, `POST /rerender`)

### `alignment_hybrid.py` — 5-Layer Hybrid Aligner
```
Layer 1: Audio Analysis      — VAD, energy-based gap detection
Layer 2: Text Matching       — global DP with rapidfuzz (Levenshtein) + jellyfish (Metaphone)
Layer 3: Structural Tagging  — verse / background / instrumental classification
Layer 4: Interpolation       — cubic spline (scipy) for unmatched words, audio-energy word boundaries
Layer 5: Quality Assurance   — monotonicity enforcement, smooth gap/overlap transitions
```
Supports 20+ languages (EN, ES, FR, DE, IT, PT, RU, ZH, JA, KO, AR, HI, and more).

### `alignment_whisperx.py` — WhisperX Alignment
Uses OpenAI Whisper for transcription + WhisperX phoneme-level forced alignment to produce word timestamps. Falls back to the hybrid engine on failure.

### `audio_utils.py` — Audio Processing Utilities
- WAV conversion (FFmpeg → pydub fallback)
- Audio normalization (pydub)
- Stem separation cascade: **Demucs → Spleeter → FFmpeg mid/side**
- Cross-correlation offset detection
- Spectral flux onset detection
- Vocal segment detection from separated stems
- Pitch tracking (autocorrelation)
- Syllable alignment refinement
- LRC / SRT export

### `video_builder.py` — Video Builder
- PIL-based text rendering (no ImageMagick dependency)
- Word-level position measurement for per-word glow highlighting
- Background: solid color / image (PIL `ImageOps.fit`) / video (MoviePy)
- Thumbnail generation: 1920×1080 PNG with title + artist text overlay
- Intro trim + trailing silence trim
- Outro overlay with configurable fade-in/out

### `config.py` — Configuration
All settings are environment-variable overridable. See [Configuration](#configuration).

---

## API Reference

### `POST /upload`
Upload media, lyrics, background, and outro files.

**Form fields:**

| Field | Type | Description |
|---|---|---|
| `audio` | File | Audio file (MP3, WAV, M4A, etc.) |
| `video` | File | Video file (MP4, MOV, etc.) — mutually exclusive with `audio` |
| `lyrics` | File | `.txt` or `.lrc` lyrics file |
| `background` | File | Background image (JPG/PNG) |
| `outro` | File | Outro audio or video file |

**Response:**
```json
{
  "success": true,
  "audio_path": "/abs/path/to/uploads/...",
  "video_path": null,
  "lyrics_path": "/abs/path/to/uploads/...",
  "outro_path": null,
  "background_path": null,
  "is_video": false
}
```

---

### `POST /generate`
Start a video generation job.

**Request body (JSON):**
```json
{
  "audio_path": "/abs/path/...",
  "video_path": null,
  "lyrics_path": "/abs/path/...",
  "font": "Arial",
  "fontsize": 70,
  "bg_color": "#000000",
  "bg_image": null,
  "outro_path": null,
  "outro_is_video": false,
  "outro_text": "Thanks for watching",
  "song_title": "My Song",
  "artist_name": "Artist Name",
  "separation_engine": "auto",
  "language": "en",
  "pause": {
    "threshold_db": "-26dB",
    "min_silence_sec": 0.56,
    "flux_window_sec": 0.21,
    "min_pause_sec": 0.2
  }
}
```

**Response:**
```json
{ "job_id": "uuid-v4", "status": "queued" }
```

---

### `GET /status/<job_id>`
Poll job status.

**Response (running):**
```json
{
  "job_id": "...",
  "status": "running",
  "progress": 72,
  "stage": "Rendering lyric video"
}
```

**Response (done):**
```json
{
  "job_id": "...",
  "status": "done",
  "progress": 100,
  "output_url": "/outputs/session/file_lyrics_meta.mp4",
  "final_output_url": "/outputs/session/file_lyrics_meta_final.mp4",
  "thumbnail_url": "/outputs/session/file_thumbnail.png",
  "alignment_url": "/alignments/file_alignment.json",
  "instrumental_video_url": "/outputs/session/file_instrumental.mp4"
}
```

---

### `POST /cancel/<job_id>`
Cancel a running job. Kills active FFmpeg/Demucs subprocess.

---

### `PATCH /alignment/<job_id>`
Save corrected alignment from the Lyric Editor.

**Request body:**
```json
{
  "fragments": [
    { "begin": "1.234", "end": "3.456", "lines": ["Hello world"], "words": [...], "y_offset": 0 }
  ]
}
```

**Response:**
```json
{ "success": true, "job_id": "...", "corrected_url": "/alignments/..._corrected.json" }
```

---

### `POST /rerender/<job_id>`
Re-render the video using the corrected alignment (skips alignment + stem separation).

**Response:**
```json
{ "job_id": "...", "rerender_job_id": "new-uuid", "status": "queued" }
```
Poll `GET /status/<rerender_job_id>` for progress.

---

### `GET /fonts`
List fonts available on the server (assets/fonts + common Windows fonts).

```json
{ "fonts": ["Arial", "Impact", "Verdana", "MyCustomFont"], "default": "Arial" }
```

---

### Static file routes

| Route | Description |
|---|---|
| `GET /outputs/<path>` | Serve rendered videos and thumbnails |
| `GET /uploads/<path>` | Serve uploaded files |
| `GET /alignments/<path>` | Serve alignment JSON files |

---

## Configuration

All settings in `backend/config.py` can be overridden via environment variables.

### Paths

| Env Var | Default | Description |
|---|---|---|
| *(auto)* | `./uploads` | Upload directory |
| *(auto)* | `./outputs` | Output directory |
| *(auto)* | `./alignments` | Alignment JSON directory |
| `FFMPEG_PATH` | `ffmpeg` | Path to FFmpeg binary |

### FFmpeg Encoding

| Env Var | Default | Description |
|---|---|---|
| `FFMPEG_THREADS` | `0` | Thread count (0 = all cores) |
| `FFMPEG_PRESET` | `faster` | Encoder preset (`ultrafast`→`veryslow`) |
| `FFMPEG_ENCODER` | `libx264` | Video encoder (`libx264`, `h264_amf`, `h264_nvenc`) |
| `FFMPEG_TUNE` | *(empty)* | Encoder tune (`zerolatency`, `film`, etc.) |
| `FFMPEG_CRF` | `16` | Constant Rate Factor (lower = higher quality) |

### Video Resolution

| Env Var | Default | Description |
|---|---|---|
| `CROONIFY_WIDTH` | `1920` | Output video width |
| `CROONIFY_HEIGHT` | `1080` | Output video height |

### Outro Overlay

| Env Var | Default | Description |
|---|---|---|
| `OUTRO_ENABLED` | `1` | Enable outro overlay (`0` to disable) |
| `OUTRO_MESSAGE_TEXT` | `Thanks for watching` | Default outro message |
| `OUTRO_FADE_IN_SEC` | `0.6` | Fade-in duration (seconds) |
| `OUTRO_FADE_OUT_SEC` | `0.6` | Fade-out duration (seconds) |
| `OUTRO_POSITION` | `lower_third` | `lower_third` or `center` |
| `OUTRO_FONT_COLOR` | `white` | Outro text color |
| `OUTRO_BOX_COLOR` | `black` | Background box color |
| `OUTRO_BOX_OPACITY` | `0.35` | Background box opacity (0–1) |

### Server Port

| Env Var | Default | Description |
|---|---|---|
| `CROONIFY_BACKEND_PORT` | `5000` | Flask server port |

---

## Lyric Editor

The Lyric Editor appears automatically after a video is generated. It consists of four JavaScript modules:

| Module | Purpose |
|---|---|
| `lyric_editor.js` | Shared state (`LE` namespace), undo/redo stack (50 steps), time helpers |
| `lyric_editor_table.js` | Editable data table — click a row to select, inline edit start/end/text |
| `lyric_editor_timeline.js` | Canvas timeline — drag segments horizontally; Y-handle for vertical offset |
| `lyric_editor_actions.js` | Save (`PATCH /alignment`), Re-render (`POST /rerender`), auto-save (4 s debounce), Reset |

### Workflow

1. Video finishes rendering → editor panel opens automatically with all lyric segments
2. Adjust timings by dragging segments on the timeline or editing the table directly
3. Drag the Y-handle to move a lyric line up/down on the video
4. Click **Save** (or wait 4 s for auto-save) — calls `PATCH /alignment/<job_id>`
5. Click **Re-render** — calls `POST /rerender/<job_id>`, polls progress, shows new download link
6. Changes persist in `alignments/<name>_alignment_corrected.json`

### Session Persistence

The backend writes a `alignments/_jobs_store.json` file whenever a job completes or an alignment is saved. On server restart, this file is loaded back into memory, so the editor endpoints (`PATCH /alignment`, `POST /rerender`) continue working without requiring a new render.

---

## Supported Formats

### Audio Input
MP3, WAV, M4A, AAC, FLAC, OGG, WMA, AIFF, AIF, MP4, WEBM, OPUS

### Video Input
MP4, MOV, AVI, MKV, WEBM

### Lyrics Input
- **Plain text** (`.txt`) — one lyric line per line
- **LRC** (`.lrc`) — standard karaoke timestamp format `[mm:ss.xx]Text`
- **Typed** — paste directly in the browser text area

### Background Image
JPG, JPEG, PNG (up to 30 MB)

### Outro
Any audio format listed above, or any video format listed above (toggle `Outro is video` in the UI)

### Fonts
Drop `.ttf`, `.otf`, or `.ttc` files into `assets/fonts/` — they appear automatically in the font picker. Common Windows fonts (Arial, Impact, Verdana, Times New Roman) are auto-detected.

---

## Performance Tuning

### GPU Acceleration
Set `FFMPEG_ENCODER=h264_amf` (AMD) or `FFMPEG_ENCODER=h264_nvenc` (NVIDIA) before starting the server. The launcher script sets `h264_amf` by default.

WhisperX automatically uses CUDA when a compatible GPU is detected.

### Faster Encoding (Lower Quality)
```powershell
$env:FFMPEG_PRESET = "ultrafast"
$env:FFMPEG_CRF    = "22"
```

### Higher Quality
```powershell
$env:FFMPEG_PRESET = "slow"
$env:FFMPEG_CRF    = "14"
```

### CPU Threads
`FFMPEG_THREADS=0` (default) lets FFmpeg use all available cores. Set to a specific number to limit CPU usage.

---

## Testing

### Unit tests
```bash
# Hybrid alignment engine unit tests
python -m pytest tests/test_hybrid_align.py -v

# Lyrics parser tests
python -m pytest tests/test_lyrics.py -v

# Full pipeline integration test
python -m pytest tests/test_pipeline.py -v
```

### End-to-end API test
```bash
# Start the backend first, then:
python scripts/test_app_e2e.py --url http://localhost:5000
```

### Alignment diagnostic tools
```bash
# Preview what the aligner produces for a specific audio + lyrics pair
python scripts/preview_alignment.py --audio path/to/song.mp3 --lyrics path/to/lyrics.txt

# Analyze alignment quality metrics
python scripts/analyze_alignment.py --alignment alignments/my_alignment.json
```

---

## Deployment

### Vercel (Serverless — frontend only)
A `vercel.json` is included for deploying the frontend as a static site. The backend must be hosted separately (Railway, Render, Fly.io, etc.) due to ML model requirements.

```json
// vercel.json — routes all requests to index.html
```

### Self-hosted (recommended)
Use the PowerShell launcher:
```powershell
.\run_croonify.ps1
```

Or run the components directly:
```bash
# Backend
python -m backend.app

# Frontend (any static server)
npx serve frontend -p 8080
```

### Docker (manual)
No Dockerfile is included, but a standard Python 3.11 image with FFmpeg works:
```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y ffmpeg
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "-m", "backend.app"]
```

---

## Recent Changes

| Version | Change |
|---|---|
| Latest | **Fix: Edit timing/position "Job not found"** — frontend now captures `editorJobId` before clearing `currentJobId`; backend persists completed job stubs to `_jobs_store.json` so the editor works after server restarts |
| Previous | Upgraded video output to 1080p HD (1920×1080) |
| Previous | Fixed pink/magenta tint in video-background mode — screen blend now operates in RGB (`gbrp`) color space |
| Previous | Added instrumental video variant (same timing, instrumental stem audio) |
| Previous | Added LRC file input support |
| Previous | Added video input mode (lyrics composited over original video) |