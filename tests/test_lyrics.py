import os
import sys
import unittest
import json

# Add the parent directory to the path so we can import the backend modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.lyrics_parser import read_lyrics, write_json

class TestLyricsParser(unittest.TestCase):
    def setUp(self):
        # Path to sample lyrics file
        self.sample_lyrics_path = os.path.join(os.path.dirname(__file__), 'sample_lyrics.txt')
        self.output_json_path = os.path.join(os.path.dirname(__file__), 'output_lyrics.json')
        
        # Count actual non-empty lines in the file
        with open(self.sample_lyrics_path, 'r', encoding='utf-8') as f:
            self.actual_line_count = len([line for line in f.readlines() if line.strip()])
    
    def test_read_lyrics(self):
        # Parse the lyrics
        parsed_lyrics = read_lyrics(self.sample_lyrics_path)
        
        # Print parsed lines
        print("\nParsed lyrics:")
        for line in parsed_lyrics:
            print(f"{line['index']}: {line['text']}")
        
        # Assert the number of parsed lines matches the actual count
        self.assertEqual(len(parsed_lyrics), self.actual_line_count, 
                         f"Expected {self.actual_line_count} lines, got {len(parsed_lyrics)}")
        
        # Assert each line has the required structure
        for i, line in enumerate(parsed_lyrics):
            self.assertIn('index', line, f"Line {i} missing 'index' key")
            self.assertIn('text', line, f"Line {i} missing 'text' key")
            self.assertEqual(line['index'], i, f"Line index should be {i}, got {line['index']}")
    
    def test_write_json(self):
        # Parse the lyrics
        parsed_lyrics = read_lyrics(self.sample_lyrics_path)
        
        # Write to JSON
        result = write_json(parsed_lyrics, self.output_json_path)
        self.assertTrue(result, "write_json should return True on success")
        
        # Verify the file exists
        self.assertTrue(os.path.exists(self.output_json_path), 
                        f"Output JSON file not created at {self.output_json_path}")
        
        # Read the JSON and verify content
        with open(self.output_json_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        
        self.assertEqual(len(json_data), self.actual_line_count, 
                         f"JSON should contain {self.actual_line_count} items")
    
    def tearDown(self):
        # Clean up the output file if it exists
        if os.path.exists(self.output_json_path):
            os.remove(self.output_json_path)

if __name__ == '__main__':
    unittest.main()