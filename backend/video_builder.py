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
from moviepy.video.fx.all import fadein, fadeout
from moviepy.video.tools.subtitles import SubtitlesClip
try:
    from backend.config import (
        ALIGN_DIR,
        UPLOAD_DIR,
        OUTPUT_DIR,
        FFMPEG_THREADS,
        FFMPEG_PRESET,
        FFMPEG_ENCODER,
        FFMPEG_CRF,
        FONTS_DIR,
        OUTRO_ENABLED,
        OUTRO_MESSAGE_TEXT,
        OUTRO_FADE_IN_SEC,
        OUTRO_FADE_OUT_SEC,
        OUTRO_POSITION,
        OUTRO_FONT_COLOR,
        OUTRO_BOX_COLOR,
        OUTRO_BOX_OPACITY,
        OUTRO_OVERLAY_LAST_SECONDS,
    )
    from backend.audio_utils import detect_tail_silence
except Exception:
    from config import (
        ALIGN_DIR,
        UPLOAD_DIR,
        OUTPUT_DIR,
        FFMPEG_THREADS,
        FFMPEG_PRESET,
        FFMPEG_ENCODER,
        FFMPEG_CRF,
        FONTS_DIR,
        OUTRO_ENABLED,
        OUTRO_MESSAGE_TEXT,
        OUTRO_FADE_IN_SEC,
        OUTRO_FADE_OUT_SEC,
        OUTRO_POSITION,
        OUTRO_FONT_COLOR,
        OUTRO_BOX_COLOR,
        OUTRO_BOX_OPACITY,
        OUTRO_OVERLAY_LAST_SECONDS,
    )
    from audio_utils import detect_tail_silence
from PIL import Image, ImageDraw, ImageFont, ImageOps
import numpy as np

# Video configuration
DEFAULT_WIDTH = int(os.environ.get('CROONIFY_WIDTH', 1920))
DEFAULT_HEIGHT = int(os.environ.get('CROONIFY_HEIGHT', 1080))
DEFAULT_FPS = 24
DEFAULT_FONT = 'Arial'
DEFAULT_FONTSIZE = 70
DEFAULT_COLOR = 'white'
DEFAULT_STROKE_COLOR = 'black'
DEFAULT_STROKE_WIDTH = 2
DEFAULT_BG_COLOR = (0, 0, 0)  # Black background
DEFAULT_FADE_IN = 0.25
DEFAULT_FADE_OUT = 0.25

def create_background(width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT, color=DEFAULT_BG_COLOR, image_path=None):
    try:
        if image_path and os.path.exists(image_path):
            src = Image.open(image_path).convert('RGB')
            try:
                fitted = ImageOps.fit(src, (width, height), Image.LANCZOS)
            except Exception:
                fitted = ImageOps.fit(src, (width, height))
            arr = np.array(fitted)
            clip = ImageClip(arr)
            return clip.set_duration(100000)
    except Exception as _img_err:
        print(f"Image background failed ({_img_err}); using color")
    try:
        safe_color = color if isinstance(color, (list, tuple)) and len(color) == 3 else DEFAULT_BG_COLOR
        safe_color = (int(max(0, min(255, safe_color[0]))),
                      int(max(0, min(255, safe_color[1]))),
                      int(max(0, min(255, safe_color[2]))))
        return ColorClip(size=(width, height), color=safe_color, duration=100000)
    except Exception:
        return ColorClip(size=(width, height), color=DEFAULT_BG_COLOR, duration=100000)

def create_text_clip(text, font=DEFAULT_FONT, fontsize=DEFAULT_FONTSIZE,
                    color=DEFAULT_COLOR, stroke_color=DEFAULT_STROKE_COLOR,
                    stroke_width=DEFAULT_STROKE_WIDTH, width=DEFAULT_WIDTH):
    """
    Create a text clip using PIL to avoid ImageMagick dependency.
    Automatically wraps long lines to fit the given width.
    """
    try:
        # Try to load a TrueType font; fall back to default
        font_obj = _load_pil_font(font, fontsize)

        # Word-wrap the text within available width (with margin)
        def _wrap_text_lines(txt, font_obj, max_w, sw, margin=60):
            max_line_w = max(100, int(max_w - margin))
            tmp_img = Image.new('RGBA', (10, 10), (0, 0, 0, 0))
            d = ImageDraw.Draw(tmp_img)

            def _measure(s):
                if not s:
                    return 0
                bb = d.textbbox((0, 0), s, font=font_obj, stroke_width=sw)
                return max(0, bb[2] - bb[0])

            def _split_long_word(word):
                parts = []
                cur = ''
                for ch in word:
                    cand = cur + ch
                    if _measure(cand) <= max_line_w or not cur:
                        cur = cand
                    else:
                        parts.append(cur)
                        cur = ch
                if cur:
                    parts.append(cur)
                return parts

            words = str(txt).split()
            lines = []
            current = ''
            for w in words:
                candidate = (w if not current else current + ' ' + w)
                if _measure(candidate) <= max_line_w:
                    current = candidate
                else:
                    if current:
                        lines.append(current)
                        current = ''
                    # Handle very long words by splitting
                    if _measure(w) > max_line_w:
                        parts = _split_long_word(w)
                        for i, p in enumerate(parts):
                            if i < len(parts) - 1:
                                lines.append(p)
                            else:
                                current = p
                    else:
                        current = w
            if current:
                lines.append(current)
            if not lines:
                lines = [str(txt)]
            return lines

        lines = _wrap_text_lines(text, font_obj, width, stroke_width)
        wrapped_text = "\n" + "\n".join(lines) if len(lines) > 1 else text

        # Measure final block size using multiline metrics
        dummy_img = Image.new('RGBA', (10, 10), (0, 0, 0, 0))
        d2 = ImageDraw.Draw(dummy_img)
        spacing = int(max(4, fontsize * 0.25))
        try:
            bbox = d2.multiline_textbbox((0, 0), wrapped_text, font=font_obj,
                                         stroke_width=stroke_width, spacing=spacing, align='center')
        except Exception:
            # Fallback to single-line bbox for safety
            bbox = d2.textbbox((0, 0), wrapped_text, font=font_obj, stroke_width=stroke_width)

        img_w = width
        block_w = max(1, bbox[2] - bbox[0])
        block_h = max(1, bbox[3] - bbox[1])
        pad_y = int(max(10, fontsize * 0.3))
        img_h = max(block_h + pad_y * 2, fontsize + 20)

        # Render centered multiline text on transparent background
        img = Image.new('RGBA', (img_w, img_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        x = img_w // 2
        y = img_h // 2
        try:
            draw.multiline_text((x, y), wrapped_text, font=font_obj, fill=color,
                                stroke_width=stroke_width, stroke_fill=stroke_color,
                                anchor='mm', spacing=spacing, align='center')
        except Exception:
            # Fallback without anchor—compute top-left for centering
            top_left_x = max(0, int((img_w - block_w) / 2))
            top_left_y = max(0, int((img_h - block_h) / 2))
            draw.multiline_text((top_left_x, top_left_y), wrapped_text, font=font_obj, fill=color,
                                stroke_width=stroke_width, stroke_fill=stroke_color,
                                spacing=spacing, align='center')

        # Convert to ImageClip
        arr = np.array(img)
        clip = ImageClip(arr)
        clip = clip.set_position('center')
        return clip
    except Exception as e:
        print(f"Error creating PIL text clip: {e}")
        # Safe fallback: render minimal text with PIL default font to avoid ImageMagick dependency
        try:
            # Use default font and simple single-line rendering
            font_obj = ImageFont.load_default()
            dummy_img = Image.new('RGBA', (10, 10), (0, 0, 0, 0))
            d = ImageDraw.Draw(dummy_img)
            bbox = d.textbbox((0, 0), text, font=font_obj)
            block_w = max(1, bbox[2] - bbox[0])
            block_h = max(1, bbox[3] - bbox[1])
            pad_y = 12
            img_w = max(width, block_w + 40)
            img_h = max(block_h + pad_y * 2, 40)
            img = Image.new('RGBA', (img_w, img_h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            top_left_x = max(0, int((img_w - block_w) / 2))
            top_left_y = max(0, int((img_h - block_h) / 2))
            try:
                draw.text((top_left_x, top_left_y), text, font=font_obj, fill=color)
            except Exception:
                draw.text((top_left_x, top_left_y), text, font=font_obj, fill='white')
            arr = np.array(img)
            clip = ImageClip(arr)
            clip = clip.set_position('center')
            return clip
        except Exception as _fallback_err:
            print(f"Secondary text fallback failed: {_fallback_err}")
            # Final minimal placeholder to avoid crashing
            arr = np.zeros((80, width, 4), dtype=np.uint8)
            clip = ImageClip(arr)
            clip = clip.set_position('center')
            return clip

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

# Helpers for word layout and timing
def _find_font_path(font_req):
    """Resolve a font by friendly name or path. Returns a file path or None."""
    if not font_req:
        return None
    # Direct path
    if isinstance(font_req, str) and os.path.isfile(font_req):
        return font_req
    name = str(font_req).strip()
    base = os.path.splitext(os.path.basename(name))[0]
    base_lower = base.lower().replace(' ', '')
    candidates = []
    # Search assets/fonts
    for ext in ('.ttf', '.otf', '.ttc'):
        candidates.append(os.path.join(FONTS_DIR, base + ext))
        candidates.append(os.path.join(FONTS_DIR, base_lower + ext))
        candidates.append(os.path.join(FONTS_DIR, name + ext))
    # Windows Font directory
    if os.name == 'nt':
        win_fonts = r"C:\\Windows\\Fonts"
        for ext in ('.ttf', '.otf', '.ttc'):
            candidates.append(os.path.join(win_fonts, base + ext))
            candidates.append(os.path.join(win_fonts, base_lower + ext))
    # Common mappings
    common_map = {
        'arial': r'C:\\Windows\\Fonts\\arial.ttf',
        'impact': r'C:\\Windows\\Fonts\\impact.ttf',
        'verdana': r'C:\\Windows\\Fonts\\verdana.ttf',
        'times': r'C:\\Windows\\Fonts\\times.ttf',
        'timesnewroman': r'C:\\Windows\\Fonts\\times.ttf',
        'edo': os.path.join(FONTS_DIR, 'edo.ttf'),
    }
    key = base_lower
    if key in common_map:
        candidates.insert(0, common_map[key])
    for c in candidates:
        try:
            if os.path.exists(c):
                return c
        except Exception:
            continue
    return None

def _load_pil_font(font_name=DEFAULT_FONT, fontsize=DEFAULT_FONTSIZE):
    path = _find_font_path(font_name)
    if path:
        try:
            return ImageFont.truetype(path, fontsize)
        except Exception:
            pass
    try:
        return ImageFont.truetype(str(font_name), fontsize)
    except Exception:
        return ImageFont.load_default()

def _escape_drawtext_text(text):
    try:
        s = str(text or "")
        s = s.replace('\\', r'\\')
        s = s.replace("'", r"\'")
        s = s.replace(":", r"\:")
        s = s.replace("%", r"\%")
        s = s.replace("\n", r"\\n")
        s = s.replace("\r", "")
        return s
    except Exception:
        return ""

def generate_thumbnail_image(title, artist, out_path,
                             bg_color=DEFAULT_BG_COLOR,
                             image_path=None,
                             font_name=DEFAULT_FONT,
                             title_fontsize=None,
                             artist_fontsize=None,
                             width=DEFAULT_WIDTH,
                             height=DEFAULT_HEIGHT):
    """Create a thumbnail image combining background and centered title/artist.

    Returns out_path on success or None on failure.
    """
    try:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        bg = None
        if image_path and os.path.exists(image_path):
            try:
                src = Image.open(image_path).convert('RGB')
                bg = ImageOps.fit(src, (width, height), Image.LANCZOS)
            except Exception:
                bg = None
        if bg is None:
            base_color = tuple(bg_color) if isinstance(bg_color, (list, tuple)) else DEFAULT_BG_COLOR
            bg = Image.new('RGB', (width, height), base_color)

        draw = ImageDraw.Draw(bg)
        fg = 'white'

        # Base sizes: thumbnails should be larger than video text
        title_fs_base = int(title_fontsize or int(DEFAULT_FONTSIZE * 1.8))
        artist_fs_base = int(artist_fontsize or max(32, int(title_fs_base * 0.7)))

        stroke_w = 0

        # Helper to measure and fit text into target width with margins
        def _measure(txt, font, sw):
            tmp = Image.new('RGBA', (10, 10), (0, 0, 0, 0))
            d = ImageDraw.Draw(tmp)
            bbox = d.textbbox((0, 0), txt, font=font, stroke_width=sw)
            return max(0, bbox[2] - bbox[0]), max(0, bbox[3] - bbox[1])

        def _fit_font(txt, desired_size):
            if not (txt and len(str(txt).strip()) > 0):
                return _load_pil_font(font_name, desired_size), desired_size
            margin = 60
            max_w = max(100, width - margin)
            size = max(24, int(desired_size))
            font_tmp = _load_pil_font(font_name, size)
            w, _ = _measure(str(txt), font_tmp, stroke_w)
            if w > max_w and w > 0:
                new_size = max(24, int(size * (max_w / float(w))))
                font_tmp = _load_pil_font(font_name, new_size)
                size = new_size
            return font_tmp, size

        # Fit fonts to width
        title_font, title_fs = _fit_font(title or '', title_fs_base)
        artist_font, artist_fs = _fit_font(artist or '', artist_fs_base)
        title_w, title_h = _measure(title or '', title_font, stroke_w)
        artist_w, artist_h = _measure(artist or '', artist_font, stroke_w)

        # Layout: title higher and artist slightly higher to match sample composition
        title_x = width // 2
        title_y = int(height * 0.32)
        artist_x = width // 2
        artist_y = int(height * 0.62)

        # Render centered text with stroke
        if title:
            if stroke_w > 0:
                draw.text((title_x, title_y), str(title), font=title_font,
                          fill=fg, stroke_width=stroke_w, stroke_fill=fg,
                          anchor='mm')
            else:
                draw.text((title_x, title_y), str(title), font=title_font,
                          fill=fg, anchor='mm')
        if artist:
            if stroke_w > 0:
                draw.text((artist_x, artist_y), str(artist), font=artist_font,
                          fill=fg, stroke_width=stroke_w, stroke_fill=fg,
                          anchor='mm')
            else:
                draw.text((artist_x, artist_y), str(artist), font=artist_font,
                          fill=fg, anchor='mm')

        # Save
        ext = os.path.splitext(out_path)[1].lower()
        if ext in ('.jpg', '.jpeg'):
            bg.save(out_path, format='JPEG', quality=92)
        else:
            bg.save(out_path, format='PNG')
        return out_path
    except Exception as e:
        print(f"Thumbnail generation failed: {e}")
        return None

def _measure_words(text, font_obj, stroke_width, video_width):
    words = text.split()
    dummy_img = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    draw = ImageDraw.Draw(dummy_img)
    widths = []
    for w in words:
        bbox = draw.textbbox((0, 0), w, font=font_obj, stroke_width=stroke_width)
        widths.append(max(0, bbox[2] - bbox[0]))
    # Estimate space width robustly
    space_bbox = draw.textbbox((0, 0), " ", font=font_obj, stroke_width=stroke_width)
    space_w = max(1, space_bbox[2] - space_bbox[0]) if space_bbox else int(DEFAULT_FONTSIZE * 0.35)
    if space_w <= 0:
        space_w = int(DEFAULT_FONTSIZE * 0.35)
    total_line_w = sum(widths) + space_w * max(0, len(words) - 1)
    start_x = max(0, int((video_width - total_line_w) / 2))
    positions = []
    x = start_x
    for w_w in widths:
        positions.append((x, w_w))
        x += w_w + space_w
    return words, positions, total_line_w

def build_lyric_video(audio_path, alignment_path, output_path=None, 
                     background_path=None, background_color=DEFAULT_BG_COLOR,
                     width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT,
                     use_highlight=False, progress_callback=None, chunk_size=10,
                     font_name=DEFAULT_FONT, fontsize=DEFAULT_FONTSIZE,
                     encoder=None, preset=None, ffmpeg_threads=None,
                     outro_audio_path=None, outro_text=None, vocal_onset=None, trim_intro=False, trim_end_silence=True, min_tail_silence=1.5,
                     pause_markers=None, pause_opacity=0.22):
    """
    Build a lyric video using MoviePy with performance optimizations
    
    Args:
        audio_path (str): Path to audio file
        alignment_path (str): Path to alignment JSON
        output_path (str, optional): Path for output video. Defaults to None.
        background_path (str, optional): Path to background image. Defaults to None.
        background_color (tuple): RGB color tuple for background
        width (int): Video width
        height (int): Video height
        use_highlight (bool): Whether to use highlight animation
        progress_callback (function, optional): Callback function for progress reporting. Defaults to None.
        chunk_size (int, optional): Number of lyrics to process in each batch for memory optimization. Defaults to 10.
    
    Returns:
        str: Path to the output video file
    """
    # Honor trim_intro parameter provided by caller (no forced override)

    # Generate default output path if not provided
    if output_path is None:
        audio_filename = os.path.basename(audio_path)
        base_name = os.path.splitext(audio_filename)[0]
        output_path = os.path.join(OUTPUT_DIR, f"{base_name}_lyrics.mp4")
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    try:
        # Load audio (we may reassign after computing trims)
        audio_clip = AudioFileClip(audio_path)
        
        # Load alignment data
        with open(alignment_path, 'r') as f:
            alignment_data = json.load(f)
        if progress_callback:
            try:
                progress_callback(0.05)  # 5% after alignment JSON load
            except Exception:
                pass
        
        # Build lyrics entries from alignment data using a unified parser
        lyrics = []
        try:
            if isinstance(alignment_data, dict) and 'fragments' in alignment_data and isinstance(alignment_data.get('fragments'), list):
                # Preferred path: enriched Aeneas format
                for fragment in alignment_data.get('fragments', []):
                    lines_field = fragment.get('lines')
                    if isinstance(lines_field, list):
                        text_val = lines_field[0] if len(lines_field) > 0 else ''
                    else:
                        text_val = lines_field or ''
                    entry = {
                        'start': float(fragment.get('begin', 0)),
                        'end': float(fragment.get('end', 0)),
                        'text': str(text_val)
                    }
                    if 'words' in fragment and isinstance(fragment['words'], list):
                        entry['words'] = fragment['words']
                    lyrics.append(entry)
            else:
                # Fallback path: accept legacy formats via the audio_utils helper
                try:
                    from backend.audio_utils import _load_alignment_intervals
                    intervals = _load_alignment_intervals(alignment_path)
                except Exception:
                    intervals = []
                for (s, e, txt) in intervals:
                    lyrics.append({'start': float(s or 0), 'end': float(e or 0), 'text': str(txt or '')})
                if not lyrics:
                    raise ValueError("No aligned intervals found in alignment JSON")
        except Exception as _align_parse_err:
            print(f"Alignment parse failed: {_align_parse_err}")
            raise

        # If a vocal onset time is provided, shift all lyric timings so the
        # first non-empty lyric aligns with the onset.
        try:
            if vocal_onset is not None and isinstance(vocal_onset, (int, float)):
                first_lyric_start = None
                for e in lyrics:
                    txt = str(e.get('text', '')).strip()
                    if not txt:
                        continue
                    s = float(e.get('start', 0) or 0)
                    if first_lyric_start is None or s < first_lyric_start:
                        first_lyric_start = s
                if first_lyric_start is not None:
                    adjust = float(first_lyric_start) - float(vocal_onset)
                    # Avoid extreme shifts; only correct realistic offsets
                    if abs(adjust) >= 0.25 and abs(adjust) <= 15.0:
                        new_lyrics = []
                        for e in lyrics:
                            s = max(0.0, float(e.get('start', 0) or 0) - adjust)
                            en = max(s, float(e.get('end', 0) or 0) - adjust)
                            ne = dict(e)
                            ne['start'] = s
                            ne['end'] = en
                            new_lyrics.append(ne)
                        lyrics = new_lyrics
        except Exception as _adj_err:
            print(f"Lyric onset shift skipped: {_adj_err}")

        # Optionally trim instrumental intro by starting audio at first lyric
        # and shifting all lyric timings to begin at 0.
        try:
            start_cut = 0.0
            end_cut = None
            # Compute first aligned lyric start and prefer vocal onset if provided
            first_start = None
            if trim_intro:
                for e in lyrics:
                    txt = str(e.get('text', '')).strip()
                    if not txt:
                        continue
                    s = float(e.get('start', 0) or 0)
                    if s > 0 and (first_start is None or s < first_start):
                        first_start = s
                # Choose a start cut based on vocal_onset when available; otherwise use first lyric start
                candidate_cut = None
                if vocal_onset is not None and isinstance(vocal_onset, (int, float)) and float(vocal_onset) > 0.0:
                    candidate_cut = float(vocal_onset)
                elif first_start is not None and first_start > 0.0:
                    candidate_cut = float(first_start)
                if candidate_cut is not None and candidate_cut > 0.0:
                    start_cut = candidate_cut
            # Compute trailing silence
            if trim_end_silence:
                try:
                    tail = detect_tail_silence(audio_path, min_tail_sec=float(min_tail_silence))
                except Exception as _tail_err:
                    tail = None
                    print(f"Tail silence detection failed: {_tail_err}")
                if tail and isinstance(tail, tuple) and len(tail) == 2:
                    tail_start, tail_end = float(tail[0]), float(tail[1])
                    if tail_start > start_cut + 0.25:
                        end_cut = tail_start
            # Apply subclip once with both cuts
            if start_cut > 0.0 or (end_cut is not None):
                try:
                    audio_clip = AudioFileClip(audio_path).subclip(start_cut, end_cut)
                except Exception as _sub_err:
                    print(f"Audio subclip failed, continuing without trims: {_sub_err}")
                # Shift lyrics to new zero
                if start_cut > 0.0:
                    new_lyrics = []
                    for e in lyrics:
                        s = max(0.0, float(e.get('start', 0) or 0) - start_cut)
                        en = max(s, float(e.get('end', 0) or 0) - start_cut)
                        ne = dict(e)
                        ne['start'] = s
                        ne['end'] = en
                        new_lyrics.append(ne)
                    lyrics = new_lyrics
        except Exception as _trim_err:
            print(f"Intro trim skipped: {_trim_err}")

        # Create background after determining final audio duration
        background = create_background(width, height, background_color, background_path)
        background = background.set_duration(audio_clip.duration)

        # Sanitize, sort, and normalize lyric timings to avoid overlaps and enforce readability
        try:
            filtered = []
            for e in lyrics:
                txt = str(e.get('text', '')).strip()
                if not txt:
                    continue
                filtered.append({
                    'start': float(e.get('start', 0) or 0),
                    'end': float(e.get('end', 0) or 0),
                    'text': txt
                })
            filtered.sort(key=lambda x: x['start'])
            sanitized = []
            total = len(filtered)
            gap_guard = 0.02
            min_dur = 0.35
            for i, e in enumerate(filtered):
                s = max(0.0, min(float(e['start']), audio_clip.duration))
                en = max(0.0, min(float(e['end']), audio_clip.duration))
                if en <= s:
                    en = min(audio_clip.duration, s + min_dur)
                next_start = None
                for j in range(i + 1, total):
                    ns_txt = filtered[j]['text']
                    ns = float(filtered[j]['start'])
                    if ns_txt:
                        next_start = ns
                        break
                if next_start is not None:
                    en = min(en, max(s, next_start - gap_guard))
                if en - s < min_dur:
                    target_end = s + min_dur
                    if next_start is not None:
                        target_end = min(target_end, next_start - gap_guard)
                    en = min(audio_clip.duration, max(s, target_end))
                sanitized.append({'start': s, 'end': en, 'text': e['text']})
            lyrics = sanitized
        except Exception as _sanitize_err:
            print(f"Lyric timing sanitize skipped: {_sanitize_err}")

        # Create text clips for each lyric
        text_clips = []
        indicator_clips = []
        
        total_lyrics = max(1, len(lyrics))
        for idx, lyric in enumerate(lyrics):
            text = str(lyric.get('text', '')).strip()
            if not text:  # Skip empty lines
                continue
    
            # Original times
            start_time = float(lyric.get('start', 0) or 0)
            end_time = float(lyric.get('end', 0) or 0)
    
            # Clamp to audio duration to guarantee final video length
            start_time = max(0.0, min(start_time, audio_clip.duration))
            end_time = max(0.0, min(end_time, audio_clip.duration))
            duration = max(0.0, end_time - start_time)
            if duration <= 0 or start_time >= audio_clip.duration:
                continue
    
            # Base text (white)
            base_clip = create_text_clip(text, font=font_name, fontsize=fontsize, width=width)
            base_clip = base_clip.set_position('center')
            # Set timing first, then apply fades (fx may require duration)
            base_clip = base_clip.set_start(start_time).set_duration(duration)
            # Fade-in/out durations capped to half the clip length
            try:
                fade_in_d = min(DEFAULT_FADE_IN, duration / 2.0)
                fade_out_d = min(DEFAULT_FADE_OUT, duration / 2.0)
                if fade_in_d > 0:
                    base_clip = base_clip.fx(fadein, fade_in_d)
                if fade_out_d > 0:
                    base_clip = base_clip.fx(fadeout, fade_out_d)
            except Exception as _fade_err:
                # Fail-safe: keep clip without fades if fx application fails
                print(f"Fade fx skipped for clip '{text}': {_fade_err}")
            text_clips.append(base_clip)

            # Per-word green highlight has been disabled for stability.
            # The previous implementation used dynamic crop functions which caused
            # runtime errors in MoviePy. If reintroducing in the future, implement
            # animated masks via a proper VideoClip make_frame-based mask.

            # Progress update during clip assembly (up to ~90%)
            if progress_callback:
                try:
                    frac = 0.05 + 0.85 * ((idx + 1) / float(total_lyrics))
                    progress_callback(min(0.9, max(0.05, frac)))
                except Exception:
                    pass
    
    
    
        if isinstance(pause_markers, list) and len(pause_markers) > 0:
            for mk in pause_markers:
                try:
                    s = float(mk.get('start', 0) or 0)
                    e = float(mk.get('end', s))
                    kind = str(mk.get('kind', 'pause'))
                    if e <= s:
                        continue
                    st = max(0.0, min(s, audio_clip.duration))
                    en = max(0.0, min(e, audio_clip.duration))
                    dur = max(0.0, en - st)
                    if dur <= 0:
                        continue
                    bar = ColorClip(size=(int(width * 0.6), 6), color=(255, 255, 255))
                    bar = bar.set_opacity(float(pause_opacity))
                    bar = bar.set_position(('center', 'top'))
                    bar = bar.set_start(st).set_duration(dur)
                    try:
                        fd = min(0.12, dur / 2.0)
                        if fd > 0:
                            bar = bar.fx(fadein, fd).fx(fadeout, fd)
                    except Exception:
                        pass
                    indicator_clips.append(bar)
                except Exception:
                    continue
        main_video = CompositeVideoClip([background] + indicator_clips + text_clips)

        # Add audio and enforce exact duration match for main section
        main_video = main_video.set_audio(audio_clip)
        main_video = main_video.set_duration(audio_clip.duration)

        final_video = main_video

        # If an outro audio is provided, append a plain background segment with the outro audio
        if outro_audio_path and os.path.exists(outro_audio_path):
            try:
                outro_clip_audio = AudioFileClip(outro_audio_path)
                outro_bg = create_background(width, height, background_color, background_path)
                outro_bg = outro_bg.set_duration(outro_clip_audio.duration)
                outro_section = CompositeVideoClip([outro_bg])
                outro_section = outro_section.set_audio(outro_clip_audio)
                outro_section = outro_section.set_duration(outro_clip_audio.duration)
                final_video = concatenate_videoclips([main_video, outro_section], method='compose')
            except Exception as e:
                print(f"Failed to append outro audio: {e}")
                final_video = main_video
    
        # Write output file
        # Final progress bump before export
        if progress_callback:
            try:
                progress_callback(0.95)
            except Exception:
                pass

        # Use ffmpeg params to maximize CPU usage and speed
        selected_encoder = (encoder or FFMPEG_ENCODER or 'libx264')
        selected_preset = preset or FFMPEG_PRESET
        selected_threads = ffmpeg_threads if ffmpeg_threads is not None else FFMPEG_THREADS

        ffparams = ['-movflags', 'faststart', '-pix_fmt', 'yuv420p']
        if selected_encoder.lower() == 'libx264':
            ffparams = ['-preset', str(selected_preset)] + ffparams
        # Ensure consistent audio parameters to match outro segment and avoid concat artifacts
        ffparams += ['-ar', '44100', '-ac', '2', '-b:a', '192k']
        # Optional tune for lower latency & faster throughput
        try:
            from backend.config import FFMPEG_TUNE
            if FFMPEG_TUNE:
                ffparams += ['-tune', str(FFMPEG_TUNE)]
        except Exception:
            pass
        # Prefer CRF; default to 20 if not configured to maintain consistent quality
        bitrate_arg = None
        if FFMPEG_CRF:
            ffparams += ['-crf', str(FFMPEG_CRF)]
        else:
            ffparams += ['-crf', '20']
        # Let ffmpeg use all logical cores when threads=0
        if selected_threads is not None:
            ffparams += ['-threads', str(selected_threads)]
        try:
            apply_overlay = (not outro_audio_path) and str(OUTRO_ENABLED).strip() in ("1", "true", "True")
            if apply_overlay and hasattr(final_video, "duration"):
                dur = float(final_video.duration or 0.0)
                last_sec = float(OUTRO_OVERLAY_LAST_SECONDS or 8.0)
                start_t = max(0.0, dur - last_sec)
                fi = float(OUTRO_FADE_IN_SEC or 0.6)
                fo = float(OUTRO_FADE_OUT_SEC or 0.6)
                boxc = f"{OUTRO_BOX_COLOR}@{OUTRO_BOX_OPACITY}" if OUTRO_BOX_COLOR else "black@0.35"
                fs = int(fontsize or DEFAULT_FONTSIZE)
                fs = max(24, min(144, int(fs)))
                fp = _find_font_path(font_name) if font_name else None
                font_expr = ("fontfile=" + fp.replace("\\", "/")) if fp else (f"font={font_name}" if font_name else "font=Arial")
                pos_y = "(h-text_h)/2"
                if str(OUTRO_POSITION).lower() == "lower_third":
                    pos_y = "h-text_h-50"
                alpha_expr = None
                if dur > 0.0 and (fi > 0.0 or fo > 0.0):
                    alpha_expr = f"if(lt(t,{start_t+fi}),(t-{start_t})/{fi},if(lt(t,{dur-fo}),1,max(0,({dur}-t)/{fo})))"
                msg = str(outro_text).strip() if outro_text is not None else ""
                if not msg:
                    msg = OUTRO_MESSAGE_TEXT
                msg = _escape_drawtext_text(msg)
                dt = (
                    f"drawtext={font_expr}:text='{msg}':x=(w-text_w)/2:y={pos_y}:fontcolor={OUTRO_FONT_COLOR}:fontsize={fs}:box=1:boxcolor={boxc}"
                    + (f":alpha='{alpha_expr}'" if alpha_expr else "")
                    + f":enable='gte(t,{start_t})'"
                )
                ffparams = ['-vf', dt] + ffparams
        except Exception:
            pass

        try:
            print(f"Video builder: assembling {len(text_clips)} clips; audio={audio_clip.duration:.3f}s")
        except Exception:
            pass
        try:
            print(f"Video builder: export start -> {output_path} (encoder={selected_encoder})")
        except Exception:
            pass
        try:
            final_video.write_videofile(
                output_path,
                fps=DEFAULT_FPS,
                audio_codec='aac',
                codec=selected_encoder,
                bitrate=bitrate_arg,
                ffmpeg_params=ffparams,
            )
        except Exception as e_primary:
            try:
                print(f"Primary encoder '{selected_encoder}' failed: {e_primary}; retrying with 'libx264'")
            except Exception:
                pass
            try:
                final_video.write_videofile(
                    output_path,
                    fps=DEFAULT_FPS,
                    audio_codec='aac',
                    codec='libx264',
                    bitrate=None,
                    ffmpeg_params=['-preset', str(selected_preset or 'medium'), '-crf', str(FFMPEG_CRF or 20), '-movflags', 'faststart', '-pix_fmt', 'yuv420p', '-threads', '0'],
                )
            except Exception as e_fallback:
                try:
                    print(f"Fallback encoder 'libx264' also failed: {e_fallback}")
                except Exception:
                    pass
                raise
    
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
    parser.add_argument("--outro", help="Path to outro audio file (optional)")
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH, help="Video width")
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT, help="Video height")
    parser.add_argument("--highlight", action="store_true", help="Use highlight animation")
    parser.add_argument("--font", help="Font name or path (e.g., 'Arial', 'edo', or path to .ttf)")
    parser.add_argument("--fontsize", type=int, default=DEFAULT_FONTSIZE, help="Font size")
    
    args = parser.parse_args()
    
    # Build video
    output_path = build_lyric_video(
        args.audio,
        args.align,
        args.out,
        None,
        DEFAULT_BG_COLOR,
        args.width,
        args.height,
        args.highlight,
        args.font,
        args.fontsize,
        outro_audio_path=args.outro
    )
    
    if output_path:
        print(f"Video created at: {output_path}")
    else:
        print("Failed to create video")
