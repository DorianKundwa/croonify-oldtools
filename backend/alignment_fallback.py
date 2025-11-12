import os
import json
import argparse
from pydub import AudioSegment
from pydub.silence import detect_silence
from lyrics_parser import read_lyrics
from config import ALIGN_DIR

def align_with_silence_detection(audio_path, lyrics_path, output_json=None):
    """
    Align audio and lyrics using pydub's silence detection.
    Falls back to equal division if silence detection doesn't work well.
    
    Args:
        audio_path (str): Path to the audio file
        lyrics_path (str): Path to the lyrics file
        output_json (str, optional): Path to save the alignment JSON. Defaults to None.
    
    Returns:
        list: List of dictionaries with start_ms, end_ms, and text for each line
    """
    try:
        # Load audio file
        audio = AudioSegment.from_file(audio_path)
        
        # Get lyrics
        lyrics = read_lyrics(lyrics_path)
        
        # Detect silences (min_silence_len in ms, silence_thresh in dB)
        silences = detect_silence(audio, min_silence_len=500, silence_thresh=-40)
        
        # If we have enough silences to match lyrics, use them for alignment
        if len(silences) >= len(lyrics) - 1:
            return align_with_detected_silences(audio, lyrics, silences, output_json)
        else:
            print(f"Not enough silences detected ({len(silences)}), falling back to equal division")
            return align_with_equal_division(audio, lyrics, output_json)
    except Exception as e:
        print(f"Error in silence detection: {e}")
        return align_with_equal_division(audio, lyrics, output_json)

def align_with_detected_silences(audio, lyrics, silences, output_json=None):
    """
    Align lyrics using detected silences as segment boundaries.
    
    Args:
        audio (AudioSegment): The audio segment
        lyrics (list): List of lyric dictionaries
        silences (list): List of silence ranges [start_ms, end_ms]
        output_json (str, optional): Path to save the alignment JSON
    
    Returns:
        list: List of dictionaries with start_ms, end_ms, and text for each line
    """
    # Create segments based on silences
    segments = []
    
    # Add first segment from start to first silence
    if silences and silences[0][0] > 0:
        segments.append([0, silences[0][0]])
    
    # Add segments between silences
    for i in range(len(silences) - 1):
        segments.append([silences[i][1], silences[i+1][0]])
    
    # Add last segment from last silence to end
    if silences and silences[-1][1] < len(audio):
        segments.append([silences[-1][1], len(audio)])
    
    # Match segments to lyrics (use as many segments as we have lyrics)
    result = []
    for i, lyric in enumerate(lyrics):
        if i < len(segments):
            result.append({
                "start_ms": segments[i][0],
                "end_ms": segments[i][1],
                "text": lyric["text"]
            })
        else:
            # If we run out of segments, use the last segment's end time
            last_end = result[-1]["end_ms"] if result else 0
            result.append({
                "start_ms": last_end,
                "end_ms": len(audio),
                "text": lyric["text"]
            })
    
    # Save result if output_json is provided
    if output_json:
        save_alignment(result, output_json)
    
    return result

def align_with_equal_division(audio, lyrics, output_json=None):
    """
    Align lyrics by dividing audio duration equally among lyric lines.
    
    Args:
        audio (AudioSegment): The audio segment
        lyrics (list): List of lyric dictionaries
        output_json (str, optional): Path to save the alignment JSON
    
    Returns:
        list: List of dictionaries with start_ms, end_ms, and text for each line
    """
    # Get audio duration in milliseconds
    duration = len(audio)
    
    # Calculate segment duration
    segment_duration = duration / len(lyrics)
    
    # Create alignment
    result = []
    for i, lyric in enumerate(lyrics):
        start_ms = int(i * segment_duration)
        end_ms = int((i + 1) * segment_duration)
        
        result.append({
            "start_ms": start_ms,
            "end_ms": end_ms,
            "text": lyric["text"]
        })
    
    # Save result if output_json is provided
    if output_json:
        save_alignment(result, output_json)
    
    return result

def save_alignment(alignment, output_json):
    """
    Save alignment to JSON file.
    
    Args:
        alignment (list): List of dictionaries with start_ms, end_ms, and text
        output_json (str): Path to save the alignment JSON
    """
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(output_json), exist_ok=True)
    
    # Save to file
    with open(output_json, 'w') as f:
        json.dump(alignment, f, indent=2)
    
    print(f"Alignment saved to {output_json}")

def align(audio_path, lyrics_path, output_json=None):
    """
    Main alignment function that serves as the entry point.
    
    Args:
        audio_path (str): Path to the audio file
        lyrics_path (str): Path to the lyrics file
        output_json (str, optional): Path to save the alignment JSON. Defaults to None.
    
    Returns:
        list: List of dictionaries with start_ms, end_ms, and text for each line
    """
    # Generate output path if not provided
    if not output_json:
        audio_filename = os.path.basename(audio_path)
        base_name = os.path.splitext(audio_filename)[0]
        output_json = os.path.join(ALIGN_DIR, f"{base_name}_alignment.json")
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(output_json), exist_ok=True)
    
    # Perform alignment
    return align_with_silence_detection(audio_path, lyrics_path, output_json)

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Align audio and lyrics using fallback methods")
    parser.add_argument("--audio", required=True, help="Path to the audio file")
    parser.add_argument("--lyrics", required=True, help="Path to the lyrics file")
    parser.add_argument("--output", help="Path to save the alignment JSON")
    
    args = parser.parse_args()
    
    # Perform alignment
    result = align(args.audio, args.lyrics, args.output)
    
    # Print result
    print(f"Generated {len(result)} alignments")
    for i, item in enumerate(result[:3]):  # Print first 3 items
        print(f"{i+1}: {item['start_ms']}ms - {item['end_ms']}ms: {item['text']}")
    
    if len(result) > 3:
        print("...")