import os

# Define directory paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')
OUTPUT_DIR = os.path.join(BASE_DIR, 'outputs')
ALIGN_DIR = os.path.join(BASE_DIR, 'alignments')
LOG_DIR = os.path.join(BASE_DIR, 'logs')

# Define FFMPEG path for Windows
FFMPEG_PATH = "ffmpeg"  # Assuming ffmpeg is in PATH, otherwise specify full path

# Create directories if they don't exist
for directory in [UPLOAD_DIR, OUTPUT_DIR, ALIGN_DIR, LOG_DIR]:
    os.makedirs(directory, exist_ok=True)