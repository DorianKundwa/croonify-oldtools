import os

# Define directory paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')
OUTPUT_DIR = os.path.join(BASE_DIR, 'outputs')
ALIGN_DIR = os.path.join(BASE_DIR, 'alignments')
LOG_DIR = os.path.join(BASE_DIR, 'logs')
ASSETS_DIR = os.path.join(BASE_DIR, 'assets')
FONTS_DIR = os.path.join(ASSETS_DIR, 'fonts')

# Define FFMPEG path for Windows (can be overridden via env var FFMPEG_PATH)
FFMPEG_PATH = os.environ.get("FFMPEG_PATH", "ffmpeg")  # If not in PATH, set FFMPEG_PATH to full exe path

# Performance tuning for FFmpeg (can be overridden via env vars)
# threads=0 lets ffmpeg auto-select the maximum number of threads (i.e., all cores)
FFMPEG_THREADS = int(os.environ.get("FFMPEG_THREADS", "0"))
# preset controls encoder speed/complexity; 'ultrafast' maximizes speed at the cost of compression efficiency
FFMPEG_PRESET = os.environ.get("FFMPEG_PRESET", "ultrafast")
# tune can further optimize for speed/latency; 'zerolatency' removes lookahead and reduces buffering
FFMPEG_TUNE = os.environ.get("FFMPEG_TUNE", "")
# encoder can be 'libx264' (CPU) or 'h264_nvenc' (NVIDIA GPU), etc.
FFMPEG_ENCODER = os.environ.get("FFMPEG_ENCODER", "libx264")
# Optional quality target. If set, we will prefer CRF over bitrate in video builder.
FFMPEG_CRF = os.environ.get("FFMPEG_CRF", "16")

# Outro overlay configuration (customizable via environment variables)
OUTRO_ENABLED = os.environ.get("OUTRO_ENABLED", "1")  # '1' to enable by default
OUTRO_MESSAGE_TEXT = os.environ.get("OUTRO_MESSAGE_TEXT", "Thanks for watching")
OUTRO_FADE_IN_SEC = float(os.environ.get("OUTRO_FADE_IN_SEC", "0.6"))
OUTRO_FADE_OUT_SEC = float(os.environ.get("OUTRO_FADE_OUT_SEC", "0.6"))
OUTRO_POSITION = os.environ.get("OUTRO_POSITION", "lower_third")  # 'lower_third' or 'center'
OUTRO_FONT_COLOR = os.environ.get("OUTRO_FONT_COLOR", "white")
OUTRO_BOX_COLOR = os.environ.get("OUTRO_BOX_COLOR", "black")
OUTRO_BOX_OPACITY = float(os.environ.get("OUTRO_BOX_OPACITY", "0.35"))
OUTRO_OVERLAY_LAST_SECONDS = float(os.environ.get("OUTRO_OVERLAY_LAST_SECONDS", "8.0"))  # when no explicit outro audio

# Create directories if they don't exist
for directory in [UPLOAD_DIR, OUTPUT_DIR, ALIGN_DIR, LOG_DIR, ASSETS_DIR, FONTS_DIR]:
    os.makedirs(directory, exist_ok=True)
