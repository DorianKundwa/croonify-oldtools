# Dorian Lyrics Maker v1

A complete web application that synchronizes lyrics with audio files and generates lyric videos with per-word highlighting.

## Features

- **Audio Upload**: Support for MP3, WAV, M4A, FLAC files up to 100MB
- **Image Upload**: Support for JPG, PNG, GIF files up to 10MB
- **Lyrics Input**: Paste lyrics or upload text files up to 1MB
- **Real-time Synchronization**: Per-word highlighting with Web Audio API
- **Cross-device Compatibility**: Responsive design optimized for all devices
- **Error Handling**: Comprehensive validation and user-friendly error messages
- **Progress Tracking**: Real-time upload and processing status
- **Video Generation**: Automatic lyric video creation with synchronized timing

## Technical Stack

- **Backend**: Flask (Python)
- **Frontend**: HTML5, CSS3, JavaScript (ES2020)
- **Audio Processing**: Web Audio API, Aeneas library
- **Video Processing**: MoviePy, PIL/Pillow
- **Deployment**: Vercel-ready configuration

## Quick Start

### Local Development

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Start the backend server:
```bash
cd backend && python app.py
```

3. Open `frontend/index.html` in your browser

### Testing

Run the complete pipeline test:
```bash
python tests/test_pipeline.py --audio uploads/sample_audio.mp3 --lyrics tests/sample_lyrics.txt
```

## File Structure

```
├── backend/
│   ├── app.py              # Flask API server
│   ├── aligner.py          # Aeneas alignment logic
│   └── video_builder.py    # Video generation
├── frontend/
│   └── index.html          # Main web interface
├── tests/
│   ├── test_pipeline.py    # End-to-end testing
│   └── sample_lyrics.txt   # Sample lyrics
├── uploads/                # Uploaded files storage
├── temp/                   # Temporary processing files
└── vercel.json            # Deployment configuration
```

## API Endpoints

- `POST /upload` - Upload audio and image files
- `POST /generate` - Generate synchronized lyrics
- `GET /status/<job_id>` - Check processing status
- `GET /download/<job_id>` - Download generated video

## Performance Optimizations

- **Responsive Design**: CSS clamp() functions for fluid typography
- **File Validation**: Size limits and format checking
- **Timeout Protection**: 5-minute upload timeout, 30-minute max processing
- **Memory Management**: Proper cleanup and resource disposal
- **Error Recovery**: Graceful handling of network and processing errors

## Deployment

Ready for deployment on Vercel with included configuration. The application is optimized for serverless deployment with appropriate timeout and size limits.