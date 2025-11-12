import os
import subprocess
import wave
from pydub import AudioSegment
from config import FFMPEG_PATH

def convert_to_wav(input_path, output_path):
    """
    Convert any audio file to mono 44.1kHz WAV using ffmpeg
    
    Args:
        input_path (str): Path to input audio file
        output_path (str): Path to output WAV file
    
    Returns:
        bool: True if conversion was successful
    """
    try:
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Build ffmpeg command
        cmd = [
            FFMPEG_PATH,
            '-i', input_path,
            '-acodec', 'pcm_s16le',  # 16-bit PCM
            '-ar', '44100',          # 44.1kHz sample rate
            '-ac', '1',              # Mono
            '-y',                    # Overwrite output file if it exists
            output_path
        ]
        
        # Run ffmpeg command
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print("Conversion complete")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error during conversion: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error: {e}")
        return False

def normalize_audio(wav_path):
    """
    Normalize audio volume using pydub
    
    Args:
        wav_path (str): Path to WAV file
    
    Returns:
        str: Path to normalized WAV file
    """
    try:
        # Load audio file
        audio = AudioSegment.from_wav(wav_path)
        
        # Normalize to -1dB
        normalized_audio = audio.normalize()
        
        # Generate output path
        filename, ext = os.path.splitext(wav_path)
        normalized_path = f"{filename}_normalized{ext}"
        
        # Export normalized audio
        normalized_audio.export(normalized_path, format="wav")
        
        return normalized_path
    except Exception as e:
        print(f"Error normalizing audio: {e}")
        return wav_path

def get_duration(wav_path):
    """
    Get the duration of a WAV file in seconds
    
    Args:
        wav_path (str): Path to WAV file
    
    Returns:
        float: Duration in seconds
    """
    try:
        with wave.open(wav_path, 'rb') as wav_file:
            # Get audio parameters
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            
            # Calculate duration
            duration = frames / float(rate)
            return duration
    except Exception as e:
        print(f"Error getting duration: {e}")
        return 0.0

# CLI test block
if __name__ == "__main__":
    # Test conversion
    convert_to_wav("tests/sample.mp3", "uploads/test.wav")
    
    # Test duration
    if os.path.exists("uploads/test.wav"):
        duration = get_duration("uploads/test.wav")
        print(f"Duration: {duration:.2f} seconds")
        
        # Test normalization
        normalized_path = normalize_audio("uploads/test.wav")
        print(f"Normalized audio saved to: {normalized_path}")
    else:
        print("Conversion failed, test.wav not found")