#!/usr/bin/env python
"""
Test script to run the entire Croonify backend pipeline on a sample audio file.
This script tests:
1. Audio conversion and normalization
2. Lyrics alignment (with aeneas or fallback)
3. Video generation
"""

import os
import sys
import time
import shutil
import argparse
from pathlib import Path

# Add the parent directory to the path so we can import the backend modules
sys.path.append(str(Path(__file__).parent.parent))

from backend.config import UPLOAD_DIR, ALIGN_DIR, OUTPUT_DIR
from backend.audio_utils import convert_to_wav, normalize_audio
from backend.alignment_aeneas import align
from backend.video_builder import build_lyric_video

def ensure_directories():
    """Ensure all required directories exist"""
    for directory in [UPLOAD_DIR, ALIGN_DIR, OUTPUT_DIR]:
        os.makedirs(directory, exist_ok=True)
    print("✓ All directories created")

def clean_directories():
    """Clean output directories to start fresh"""
    for directory in [UPLOAD_DIR, ALIGN_DIR, OUTPUT_DIR]:
        if os.path.exists(directory):
            for file in os.listdir(directory):
                file_path = os.path.join(directory, file)
                if os.path.isfile(file_path):
                    os.unlink(file_path)
    print("✓ Directories cleaned")

def run_pipeline(audio_file, lyrics_file, clean=False):
    """Run the entire backend pipeline"""
    start_time = time.time()
    
    # Clean directories if requested
    if clean:
        clean_directories()
    
    # Ensure directories exist
    ensure_directories()
    
    # Step 1: Copy files to uploads directory
    audio_filename = os.path.basename(audio_file)
    lyrics_filename = os.path.basename(lyrics_file)
    
    upload_audio_path = os.path.join(UPLOAD_DIR, audio_filename)
    upload_lyrics_path = os.path.join(UPLOAD_DIR, lyrics_filename)
    
    shutil.copy2(audio_file, upload_audio_path)
    shutil.copy2(lyrics_file, upload_lyrics_path)
    
    print(f"✓ Files copied to uploads directory")
    print(f"  - Audio: {upload_audio_path}")
    print(f"  - Lyrics: {upload_lyrics_path}")
    
    # Step 2: Convert audio to WAV if needed
    wav_filename = f"{os.path.splitext(audio_filename)[0]}.wav"
    wav_path = os.path.join(UPLOAD_DIR, wav_filename)
    
    if not audio_filename.lower().endswith('.wav'):
        convert_to_wav(upload_audio_path, wav_path)
        print(f"✓ Audio converted to WAV: {wav_path}")
    else:
        wav_path = upload_audio_path
        print(f"✓ Audio already in WAV format: {wav_path}")
    
    # Step 3: Normalize audio
    normalize_audio(wav_path, wav_path)
    print(f"✓ Audio normalized: {wav_path}")
    
    # Step 4: Align audio with lyrics
    alignment_path = os.path.join(ALIGN_DIR, f"{os.path.splitext(audio_filename)[0]}_alignment.json")
    align(wav_path, upload_lyrics_path, alignment_path)
    print(f"✓ Audio aligned with lyrics: {alignment_path}")
    
    # Step 5: Build video
    output_path = os.path.join(OUTPUT_DIR, f"{os.path.splitext(audio_filename)[0]}_lyrics.mp4")
    build_lyric_video(wav_path, alignment_path, output_path)
    print(f"✓ Lyric video created: {output_path}")
    
    # Calculate total time
    end_time = time.time()
    total_time = end_time - start_time
    print(f"\nTotal pipeline execution time: {total_time:.2f} seconds")
    
    # Verify all files were created
    verify_files = [
        upload_audio_path,
        upload_lyrics_path,
        wav_path,
        alignment_path,
        output_path
    ]
    
    all_files_exist = True
    for file_path in verify_files:
        if not os.path.exists(file_path):
            print(f"❌ Missing file: {file_path}")
            all_files_exist = False
    
    if all_files_exist:
        print("\n✅ All files were successfully generated!")
        print("\nDirectory contents:")
        print(f"- Uploads: {len(os.listdir(UPLOAD_DIR))} files")
        print(f"- Alignments: {len(os.listdir(ALIGN_DIR))} files")
        print(f"- Outputs: {len(os.listdir(OUTPUT_DIR))} files")
    else:
        print("\n❌ Some files are missing. Pipeline test failed.")
    
    return all_files_exist

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test the Croonify backend pipeline")
    parser.add_argument("--audio", required=True, help="Path to audio file (MP3 or WAV)")
    parser.add_argument("--lyrics", required=True, help="Path to lyrics file (TXT)")
    parser.add_argument("--clean", action="store_true", help="Clean directories before running")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.audio):
        print(f"Error: Audio file not found: {args.audio}")
        sys.exit(1)
    
    if not os.path.exists(args.lyrics):
        print(f"Error: Lyrics file not found: {args.lyrics}")
        sys.exit(1)
    
    success = run_pipeline(args.audio, args.lyrics, args.clean)
    
    if success:
        print("\nPipeline test completed successfully!")
        sys.exit(0)
    else:
        print("\nPipeline test failed!")
        sys.exit(1)