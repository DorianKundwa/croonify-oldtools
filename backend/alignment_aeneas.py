import os
import sys
import json
import argparse
from config import ALIGN_DIR

# Try to import aeneas
try:
    from aeneas.executetask import ExecuteTask
    from aeneas.task import Task
    AENEAS_AVAILABLE = True
except ImportError:
    AENEAS_AVAILABLE = False
    print("Warning: aeneas not available. Alignment will use fallback method.")

# Import fallback alignment module
from backend.alignment_fallback import align as align_fallback

def align(audio_path, lyrics_path, output_json=None):
    """
    Align audio with lyrics using aeneas, with fallback to pydub-based methods
    
    Args:
        audio_path (str): Path to audio file (WAV format recommended)
        lyrics_path (str): Path to lyrics text file
        output_json (str, optional): Path to output JSON file. If None, a default path will be used.
    
    Returns:
        str: Path to the output JSON file with alignment data or
        list: List of alignment dictionaries if using fallback method
    """
    # Generate default output path if not provided
    if output_json is None:
        # Create a filename based on the audio filename
        audio_filename = os.path.basename(audio_path)
        base_name = os.path.splitext(audio_filename)[0]
        output_json = os.path.join(ALIGN_DIR, f"{base_name}_alignment.json")
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_json), exist_ok=True)
    
    # Check if aeneas is available
    if not AENEAS_AVAILABLE:
        print("Aeneas not available. Using fallback alignment method.")
        return align_fallback(audio_path, lyrics_path, output_json)
    
    try:
        # Configure aeneas task
        config_string = "task_language=eng|is_text_type=plain|os_task_file_format=json"
        
        # Create Task object
        task = Task(config_string=config_string)
        task.audio_file_path_absolute = audio_path
        task.text_file_path_absolute = lyrics_path
        task.sync_map_file_path_absolute = output_json
        
        # Process the alignment
        executor = ExecuteTask(task)
        result = executor.execute()
        
        if result:
            print(f"Alignment completed successfully. Output saved to: {output_json}")
            return output_json
        else:
            print("Aeneas alignment failed. Using fallback alignment method.")
            return align_fallback(audio_path, lyrics_path, output_json)
            
    except Exception as e:
        print(f"Error during aeneas alignment: {e}")
        print("Using fallback alignment method.")
        return align_fallback(audio_path, lyrics_path, output_json)

def parse_alignment_json(json_path):
    """
    Parse the alignment JSON file and return a more usable format.
    Handles both aeneas format and fallback format.
    
    Args:
        json_path (str): Path to alignment JSON file
    
    Returns:
        list: List of dictionaries with start, end, and text for each line
    """
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Check if this is fallback format (list of dicts with start_ms, end_ms, text)
        if isinstance(data, list) and len(data) > 0 and 'start_ms' in data[0]:
            result = []
            for i, item in enumerate(data):
                result.append({
                    'index': i,
                    'start': item['start_ms'] / 1000.0,  # Convert ms to seconds
                    'end': item['end_ms'] / 1000.0,      # Convert ms to seconds
                    'text': item['text']
                })
            return result
        
        # Otherwise, assume aeneas format
        fragments = data.get('fragments', [])
        result = []
        
        for i, fragment in enumerate(fragments):
            result.append({
                'index': i,
                'start': float(fragment.get('begin', 0)),
                'end': float(fragment.get('end', 0)),
                'text': fragment.get('lines', [''])[0]
            })
        
        return result
    except Exception as e:
        print(f"Error parsing alignment JSON: {e}")
        return []

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Align audio and lyrics using aeneas (with fallback)")
    parser.add_argument("--audio", required=True, help="Path to the audio file")
    parser.add_argument("--lyrics", required=True, help="Path to the lyrics file")
    parser.add_argument("--output", help="Path to save the alignment JSON")
    
    args = parser.parse_args()
    
    # Perform alignment
    result = align(args.audio, args.lyrics, args.output)
    
    # If result is a string (path to JSON), parse it
    if isinstance(result, str):
        alignments = parse_alignment_json(result)
        print(f"Generated {len(alignments)} alignments")
        for i, item in enumerate(alignments[:3]):  # Print first 3 items
            print(f"{i+1}: {item['start']}s - {item['end']}s: {item['text']}")
    # If result is already a list (from fallback), it's already in the right format
    elif isinstance(result, list):
        print(f"Generated {len(result)} alignments using fallback method")
        for i, item in enumerate(result[:3]):  # Print first 3 items
            print(f"{i+1}: {item['start_ms']/1000}s - {item['end_ms']/1000}s: {item['text']}")
    
    if result and (isinstance(result, list) and len(result) > 3) or (isinstance(result, str) and len(alignments) > 3):
        print("...")