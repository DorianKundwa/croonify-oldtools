import os
import json
import argparse
from moviepy.editor import (
    AudioFileClip, 
    TextClip, 
    ColorClip, 
    ImageClip, 
    CompositeVideoClip, 
    concatenate_videoclips
)
from moviepy.video.tools.subtitles import SubtitlesClip
from backend.config import ALIGN_DIR, UPLOAD_DIR, OUTPUT_DIR

# Video configuration
DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080
DEFAULT_FPS = 24
DEFAULT_FONT = 'Arial'
DEFAULT_FONTSIZE = 70
DEFAULT_COLOR = 'white'
DEFAULT_STROKE_COLOR = 'black'
DEFAULT_STROKE_WIDTH = 2
DEFAULT_BG_COLOR = (0, 0, 0)  # Black background

def create_background(width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT, color=DEFAULT_BG_COLOR, image_path=None):
    """
    Create a background clip using either a color or an image
    
    Args:
        width (int): Width of the video
        height (int): Height of the video
        color (tuple): RGB color tuple for background if no image
        image_path (str, optional): Path to background image. Defaults to None.
    
    Returns:
        VideoClip: Background clip
    """
    if image_path and os.path.exists(image_path):
        try:
            # Load and resize image to fit video dimensions
            bg_clip = ImageClip(image_path)
            bg_clip = bg_clip.resize(height=height) if bg_clip.h < bg_clip.w else bg_clip.resize(width=width)
            
            # Center crop if needed
            if bg_clip.w > width:
                x_start = (bg_clip.w - width) // 2
                bg_clip = bg_clip.crop(x1=x_start, x2=x_start + width)
            if bg_clip.h > height:
                y_start = (bg_clip.h - height) // 2
                bg_clip = bg_clip.crop(y1=y_start, y2=y_start + height)
                
            return bg_clip.set_duration(100000)  # Long duration, will be cut later
        except Exception as e:
            print(f"Error loading background image: {e}")
            print("Falling back to color background")
    
    # Create color background
    return ColorClip(size=(width, height), color=color, duration=100000)

def create_text_clip(text, font=DEFAULT_FONT, fontsize=DEFAULT_FONTSIZE, 
                    color=DEFAULT_COLOR, stroke_color=DEFAULT_STROKE_COLOR, 
                    stroke_width=DEFAULT_STROKE_WIDTH):
    """
    Create a text clip for a lyric line
    
    Args:
        text (str): Text content
        font (str): Font name
        fontsize (int): Font size
        color (str): Text color
        stroke_color (str): Outline color
        stroke_width (int): Outline width
    
    Returns:
        TextClip: Configured text clip
    """
    return TextClip(
        text, 
        font=font, 
        fontsize=fontsize, 
        color=color,
        stroke_color=stroke_color,
        stroke_width=stroke_width,
        method='caption',
        align='center',
        size=(DEFAULT_WIDTH, None)
    )

def create_highlight_mask(text_clip, progress, direction='left-to-right'):
    """
    Create a mask for text highlighting animation
    
    Args:
        text_clip (TextClip): The text clip to highlight
        progress (float): Progress from 0.0 to 1.0
        direction (str): Direction of highlight ('left-to-right', 'right-to-left')
    
    Returns:
        TextClip: Highlighted text clip
    """
    w, h = text_clip.size
    
    if direction == 'left-to-right':
        highlight_width = int(w * progress)
        mask = ColorClip(size=(highlight_width, h), color=(255, 255, 255))
        mask = mask.set_position(('left', 'center'))
    elif direction == 'right-to-left':
        highlight_width = int(w * progress)
        mask = ColorClip(size=(highlight_width, h), color=(255, 255, 255))
        mask = mask.set_position(('right', 'center'))
    else:  # center-out
        highlight_width = int(w * progress)
        mask = ColorClip(size=(highlight_width, h), color=(255, 255, 255))
        mask = mask.set_position('center')
    
    return mask

def build_lyric_video(audio_path, alignment_path, output_path=None, 
                     background_path=None, background_color=DEFAULT_BG_COLOR,
                     width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT,
                     use_highlight=False):
    """
    Build a lyric video using MoviePy
    
    Args:
        audio_path (str): Path to audio file
        alignment_path (str): Path to alignment JSON
        output_path (str, optional): Path for output video. Defaults to None.
        background_path (str, optional): Path to background image. Defaults to None.
        background_color (tuple): RGB color tuple for background
        width (int): Video width
        height (int): Video height
        use_highlight (bool): Whether to use highlight animation
    
    Returns:
        str: Path to the output video file
    """
    # Generate default output path if not provided
    if output_path is None:
        audio_filename = os.path.basename(audio_path)
        base_name = os.path.splitext(audio_filename)[0]
        output_path = os.path.join(OUTPUT_DIR, f"{base_name}_lyrics.mp4")
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    try:
        # Load audio
        audio_clip = AudioFileClip(audio_path)
        
        # Create background
        background = create_background(width, height, background_color, background_path)
        background = background.set_duration(audio_clip.duration)
        
        # Load alignment data
        with open(alignment_path, 'r') as f:
            alignment_data = json.load(f)
        
        # Check if alignment data is in aeneas format or fallback format
        if isinstance(alignment_data, list) and 'start_ms' in alignment_data[0]:
            # Fallback format
            lyrics = [
                {
                    'start': item['start_ms'] / 1000.0,
                    'end': item['end_ms'] / 1000.0,
                    'text': item['text']
                }
                for item in alignment_data
            ]
        elif 'fragments' in alignment_data:
            # Aeneas format
            lyrics = [
                {
                    'start': float(fragment.get('begin', 0)),
                    'end': float(fragment.get('end', 0)),
                    'text': fragment.get('lines', [''])[0]
                }
                for fragment in alignment_data.get('fragments', [])
            ]
        else:
            # Try to parse as generic JSON
            lyrics = alignment_data
        
        # Create text clips for each lyric
        text_clips = []
        
        for lyric in lyrics:
            if not lyric['text'].strip():  # Skip empty lines
                continue
                
            # Create text clip
            txt_clip = create_text_clip(lyric['text'])
            
            # Set timing
            start_time = lyric['start']
            duration = lyric['end'] - lyric['start']
            
            # Position at bottom center with padding
            txt_clip = txt_clip.set_position(('center', 'bottom'))
            txt_clip = txt_clip.margin(bottom=100, opacity=0)
            
            # Set timing
            txt_clip = txt_clip.set_start(start_time).set_duration(duration)
            
            # Add to list
            text_clips.append(txt_clip)
        
        # Combine clips
        video = CompositeVideoClip([background] + text_clips)
        
        # Add audio
        video = video.set_audio(audio_clip)
        
        # Write output file
        video.write_videofile(
            output_path,
            fps=DEFAULT_FPS,
            codec='libx264',
            audio_codec='aac',
            threads=4
        )
        
        print(f"Video created successfully: {output_path}")
        return output_path
        
    except Exception as e:
        print(f"Error building lyric video: {e}")
        return None

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Build a lyric video using MoviePy")
    parser.add_argument("--audio", required=True, help="Path to the audio file")
    parser.add_argument("--align", required=True, help="Path to the alignment JSON file")
    parser.add_argument("--out", help="Path to save the output video")
    parser.add_argument("--bg", help="Path to background image (optional)")
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH, help="Video width")
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT, help="Video height")
    parser.add_argument("--highlight", action="store_true", help="Use highlight animation")
    
    args = parser.parse_args()
    
    # Build video
    output_path = build_lyric_video(
        args.audio,
        args.align,
        args.out,
        args.bg,
        DEFAULT_BG_COLOR,
        args.width,
        args.height,
        args.highlight
    )
    
    if output_path:
        print(f"Video created at: {output_path}")
    else:
        print("Failed to create video")