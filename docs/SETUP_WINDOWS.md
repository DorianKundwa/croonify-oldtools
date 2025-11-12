# Croonify Setup Guide for Windows

This guide will help you set up Croonify on your Windows system.

## Prerequisites

### 1. Install Python 3.7

1. Download Python 3.7 from the [official Python website](https://www.python.org/downloads/release/python-379/)
2. Select the Windows installer (64-bit) version
3. Run the installer
4. **Important**: Check the box that says "Add Python 3.7 to PATH"
5. Click "Install Now"
6. Verify installation by opening Command Prompt and typing:
   ```
   python --version
   ```
   You should see "Python 3.7.x"

### 2. Install FFmpeg

FFmpeg is required for audio and video processing:

1. Download FFmpeg from [ffmpeg.org](https://ffmpeg.org/download.html) or [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) (recommended for Windows)
2. Download the "essentials" build
3. Extract the ZIP file to a location on your computer (e.g., `C:\ffmpeg`)
4. Add FFmpeg to your PATH:
   - Right-click on "This PC" or "My Computer" and select "Properties"
   - Click on "Advanced system settings"
   - Click on "Environment Variables"
   - Under "System variables", find and select "Path", then click "Edit"
   - Click "New" and add the path to the FFmpeg `bin` folder (e.g., `C:\ffmpeg\bin`)
   - Click "OK" on all dialogs to save changes
5. Verify installation by opening a new Command Prompt and typing:
   ```
   ffmpeg -version
   ```
   You should see FFmpeg version information

## Setting Up Croonify

### 1. Install Required Python Packages

1. Open Command Prompt
2. Navigate to the Croonify project directory:
   ```
   cd path\to\croonify-oldtools
   ```
3. Install the required packages:
   ```
   pip install -r requirements.txt
   ```

### 2. Start the Backend Server

1. From the project directory, run:
   ```
   python backend/app.py
   ```
2. You should see a message indicating that the server is running on http://0.0.0.0:5000

### 3. Open the Frontend

1. Navigate to the `frontend` folder in File Explorer
2. Double-click on `index.html` to open it in your default web browser
3. The Croonify interface should now be loaded and ready to use

## Using Croonify

1. Upload an audio file (MP3 or WAV)
2. Upload a lyrics file (TXT)
3. Click "Generate Lyric Video"
4. Wait for processing to complete
5. The generated video will be displayed in the browser when ready

## Troubleshooting

### Aeneas Installation Issues

If you encounter issues with the aeneas package:

1. The application will automatically fall back to a simpler alignment method
2. For better alignment results, follow the [aeneas installation guide](https://github.com/readbeyond/aeneas/blob/master/wiki/INSTALL.md#windows-install)

### FFmpeg Not Found

If you see errors related to FFmpeg:

1. Make sure FFmpeg is correctly added to your PATH
2. Try restarting your Command Prompt or computer
3. Verify the installation with `ffmpeg -version`

### Server Connection Issues

If the frontend cannot connect to the backend:

1. Make sure the backend server is running
2. Check that you're using http://localhost:5000 in the browser
3. Check if any firewall or antivirus software is blocking the connection

## Running Tests

To test the entire pipeline:

1. Open Command Prompt
2. Navigate to the project directory
3. Run:
   ```
   python tests/test_pipeline.py --audio tests/sample.mp3 --lyrics tests/sample_lyrics.txt
   ```
4. This will test the entire pipeline and verify that all files are generated correctly