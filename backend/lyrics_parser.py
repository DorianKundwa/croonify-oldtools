import os
import json

def read_lyrics(file_path):
    """
    Read lyrics from a text file, split into lines, and remove empty ones
    
    Args:
        file_path (str): Path to lyrics text file
    
    Returns:
        list: List of dictionaries with index and text for each line
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            # Read all lines and strip whitespace
            lines = [line.strip() for line in file.readlines()]
            
            # Remove empty lines
            lines = [line for line in lines if line]
            
            # Create structured data
            parsed_lyrics = [{"index": i, "text": line} for i, line in enumerate(lines)]
            
            return parsed_lyrics
    except Exception as e:
        print(f"Error reading lyrics file: {e}")
        return []

def write_json(data, output_path):
    """
    Write parsed lyrics to a JSON file
    
    Args:
        data (list): Parsed lyrics data
        output_path (str): Path to output JSON file
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Write JSON file
        with open(output_path, 'w', encoding='utf-8') as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
        
        return True
    except Exception as e:
        print(f"Error writing JSON file: {e}")
        return False

# Simple test if run directly
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        lyrics_file = sys.argv[1]
        parsed = read_lyrics(lyrics_file)
        print(f"Parsed {len(parsed)} lines from {lyrics_file}")
        
        # Print first few lines
        for line in parsed[:5]:
            print(f"{line['index']}: {line['text']}")
            
        # Save to JSON if requested
        if len(sys.argv) > 2:
            output_file = sys.argv[2]
            if write_json(parsed, output_file):
                print(f"Saved parsed lyrics to {output_file}")
    else:
        print("Usage: python lyrics_parser.py <lyrics_file> [output_json]")