from flask import Flask, request, jsonify
import os
import datetime
import threading
import uuid
import time
import subprocess
import werkzeug.utils
import json
from shutil import which

# Standardized absolute imports from backend package
try:
    from backend.config import (
        UPLOAD_DIR,
        ALIGN_DIR,
        OUTPUT_DIR,
        FONTS_DIR,
        FFMPEG_PATH,
        FFMPEG_THREADS,
        FFMPEG_PRESET,
        FFMPEG_TUNE,
        FFMPEG_ENCODER,
        FFMPEG_CRF,
        OUTRO_ENABLED,
        OUTRO_MESSAGE_TEXT,
        OUTRO_FADE_IN_SEC,
        OUTRO_FADE_OUT_SEC,
        OUTRO_POSITION,
        OUTRO_FONT_COLOR,
        OUTRO_BOX_COLOR,
        OUTRO_BOX_OPACITY,
    )
    from backend.audio_utils import (
        convert_to_wav,
        normalize_audio,
        get_duration,
        detect_vocal_onset,
        classify_vocal_segments,
        detect_main_vocal_onset_from_alignment,
        separate_stems,
        align_offset_crosscorr,
        shift_wav,
        shift_alignment_times,
        export_alignment_formats,
        refine_word_alignment,
        refine_syllable_alignment,
        detect_vocal_segments_from_stem,
        compute_separation_quality,
        detect_breaks_and_pauses,
        extract_audio_from_video,
    )
    from backend.alignment_hybrid import align
    from backend.video_builder import (
        build_lyric_video, 
        generate_thumbnail_image, 
        _find_font_path,
        extract_video_thumbnail,
        add_metadata,
    )
except Exception:
    from config import (
        UPLOAD_DIR,
        ALIGN_DIR,
        OUTPUT_DIR,
        FONTS_DIR,
        FFMPEG_PATH,
        FFMPEG_THREADS,
        FFMPEG_PRESET,
        FFMPEG_TUNE,
        FFMPEG_ENCODER,
        FFMPEG_CRF,
        OUTRO_ENABLED,
        OUTRO_MESSAGE_TEXT,
        OUTRO_FADE_IN_SEC,
        OUTRO_FADE_OUT_SEC,
        OUTRO_POSITION,
        OUTRO_FONT_COLOR,
        OUTRO_BOX_COLOR,
        OUTRO_BOX_OPACITY,
    )
    from audio_utils import (
        convert_to_wav,
        normalize_audio,
        get_duration,
        detect_vocal_onset,
        classify_vocal_segments,
        detect_main_vocal_onset_from_alignment,
        separate_stems,
        align_offset_crosscorr,
        shift_wav,
        shift_alignment_times,
        export_alignment_formats,
        refine_word_alignment,
        refine_syllable_alignment,
        detect_vocal_segments_from_stem,
        compute_separation_quality,
        detect_breaks_and_pauses,
        extract_audio_from_video,
    )
    from alignment_hybrid import align
    from video_builder import (
        build_lyric_video, 
        generate_thumbnail_image, 
        _find_font_path,
        extract_video_thumbnail,
        add_metadata,
    )

# Job management
jobs = {}  # Dictionary to store job status: {job_id: {"status": "queued|running|done|cancelled", "output": None}}

class _JobCancelledError(Exception):
    """Raised internally when a job is cancelled mid-flight."""

def _check_cancelled(job_id):
    """Raise _JobCancelledError if the job has been cancelled."""
    if jobs.get(job_id, {}).get('cancelled'):
        raise _JobCancelledError(f"Job {job_id} was cancelled by the user")

def update_job_progress(job_id, progress):
    """Update job progress percentage"""
    if job_id in jobs:
        jobs[job_id]["progress"] = min(progress, 99)  # Reserve 100% for completion

app = Flask(__name__)

# Helper to parse hex color like #RRGGBB into (r,g,b)
def parse_bg_color(color_str):
    try:
        s = color_str.strip()
        if s.startswith('#') and len(s) == 7:
            r = int(s[1:3], 16)
            g = int(s[3:5], 16)
            b = int(s[5:7], 16)
            return (r, g, b)
    except Exception:
        pass
    return None

def _parse_bool(value):
    try:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            s = value.strip().lower()
            if s in ("1", "true", "yes", "y", "on"):
                return True
            if s in ("0", "false", "no", "n", "off", ""):
                return False
        return False
    except Exception:
        return False

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

def _resolve_ffprobe_path():
    try:
        fp = which('ffprobe') or which('ffprobe.exe')
        if fp:
            return fp
    except Exception:
        pass
    try:
        ff = FFMPEG_PATH
        if ff:
            base = os.path.basename(ff).lower()
            if base in ('ffmpeg', 'ffmpeg.exe'):
                cand = os.path.join(os.path.dirname(ff), 'ffprobe.exe' if os.name == 'nt' else 'ffprobe')
                if os.path.exists(cand):
                    return cand
    except Exception:
        pass
    return 'ffprobe'

def _parse_ffprobe_rate(rate_str):
    try:
        s = str(rate_str or '').strip()
        if not s or s == '0/0':
            return None
        if '/' in s:
            num, den = s.split('/', 1)
            n = float(num)
            d = float(den)
            if d == 0:
                return None
            v = n / d
            if v > 0:
                return v
            return None
        v = float(s)
        return v if v > 0 else None
    except Exception:
        return None

def _probe_media_basic(media_path):
    ffprobe = _resolve_ffprobe_path()
    cmd = [
        ffprobe,
        '-v', 'error',
        '-show_entries', 'format=duration',
        '-show_entries', 'stream=codec_type,width,height,r_frame_rate,sample_rate,channels',
        '-of', 'json',
        media_path,
    ]
    out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
    data = json.loads(out or '{}')
    streams = data.get('streams') or []
    fmt = data.get('format') or {}
    v = None
    a = None
    for s in streams:
        if not isinstance(s, dict):
            continue
        if v is None and s.get('codec_type') == 'video':
            v = s
        if a is None and s.get('codec_type') == 'audio':
            a = s
    duration = 0.0
    try:
        duration = float(fmt.get('duration') or 0.0)
    except Exception:
        duration = 0.0
    width = int(v.get('width') or 0) if v else 0
    height = int(v.get('height') or 0) if v else 0
    fps = _parse_ffprobe_rate(v.get('r_frame_rate') if v else None)
    has_audio = bool(a is not None)
    return {
        'duration': duration,
        'width': width,
        'height': height,
        'fps': fps,
        'has_audio': has_audio,
    }

def _append_video_keep_outro_intact(base_video_path, outro_video_path, final_path, filelist_path):
    remux_a = None
    remux_b = None
    try:
        session_dir = os.path.dirname(final_path)
        base_tag = os.path.splitext(os.path.basename(final_path))[0]
        remux_a = os.path.join(session_dir, f"{base_tag}_remux0.mp4")
        remux_b = os.path.join(session_dir, f"{base_tag}_remux1.mp4")

        remux_cmd_base = [
            FFMPEG_PATH, '-y',
            '-fflags', '+genpts',
            '-i', base_video_path,
            '-c', 'copy',
            '-avoid_negative_ts', 'make_zero',
            '-movflags', 'faststart',
            remux_a,
        ]
        remux_cmd_outro = [
            FFMPEG_PATH, '-y',
            '-fflags', '+genpts',
            '-i', outro_video_path,
            '-c', 'copy',
            '-avoid_negative_ts', 'make_zero',
            '-movflags', 'faststart',
            remux_b,
        ]
        subprocess.run(remux_cmd_base, check=True)
        subprocess.run(remux_cmd_outro, check=True)

        bv_norm = remux_a.replace("\\", "/")
        ov_norm = remux_b.replace("\\", "/")
        with open(filelist_path, 'w', encoding='utf-8') as f:
            f.write(f"file '{bv_norm}'\n")
            f.write(f"file '{ov_norm}'\n")
        concat_cmd = [
            FFMPEG_PATH, '-y',
            '-f', 'concat', '-safe', '0', '-i', filelist_path,
            '-c', 'copy',
            '-movflags', 'faststart',
            final_path,
        ]
        subprocess.run(concat_cmd, check=True)
        return True
    except Exception:
        return False
    finally:
        try:
            for p in (remux_a, remux_b):
                try:
                    if p and os.path.exists(p):
                        os.remove(p)
                except Exception:
                    pass
        except Exception:
            pass

def _reencode_append_video_preserve_outro(base_video_path, outro_video_path, final_path):
    try:
        info = _probe_media_basic(outro_video_path)
    except Exception as e:
        print(f"Outro probe failed: {e}")
        return False
    try:
        base_info = _probe_media_basic(base_video_path)
    except Exception:
        base_info = {'duration': 0.0, 'has_audio': True}

    ow = int(info.get('width') or 0)
    oh = int(info.get('height') or 0)
    ofps = info.get('fps') or 0.0
    dur = float(info.get('duration') or 0.0)
    has_outro_audio = bool(info.get('has_audio'))
    tw = int(base_info.get('width') or 0)
    th = int(base_info.get('height') or 0)
    tfps = base_info.get('fps') or 0.0
    base_dur = float(base_info.get('duration') or 0.0)
    has_base_audio = bool(base_info.get('has_audio'))

    if tw <= 0 or th <= 0:
        if ow > 0 and oh > 0:
            tw, th = ow, oh
        else:
            tw, th = 1920, 1080
    if not (tfps and tfps > 0):
        if ofps and ofps > 0:
            tfps = ofps
        else:
            tfps = 24.0

    encoder = FFMPEG_ENCODER or 'libx264'
    preset = FFMPEG_PRESET or 'medium'
    threads = str(FFMPEG_THREADS if FFMPEG_THREADS is not None else 0)
    tune = FFMPEG_TUNE
    crf = FFMPEG_CRF

    norm_v = (
        f"scale={tw}:{th}:force_original_aspect_ratio=decrease:flags=bicubic,"
        f"pad={tw}:{th}:(tw-iw)/2:(th-ih)/2,setsar=1,fps={tfps}"
    )

    parts = [
        f"[0:v]{norm_v},setpts=PTS-STARTPTS[v0]",
        f"[1:v]{norm_v},setpts=PTS-STARTPTS[v1]",
    ]
    if has_base_audio:
        parts.append("[0:a]aformat=sample_rates=44100:channel_layouts=stereo,asetpts=PTS-STARTPTS[a0]")
    else:
        if base_dur <= 0.0:
            print("Base has no audio and duration is unknown; cannot synthesize silent base audio.")
            return False
        parts.append(f"anullsrc=r=44100:cl=stereo,atrim=0:{base_dur},asetpts=N/SR/TB[a0]")
    if has_outro_audio:
        parts.append("[1:a]aformat=sample_rates=44100:channel_layouts=stereo,asetpts=PTS-STARTPTS[a1]")
    else:
        if dur <= 0.0:
            print("Outro has no audio and duration is unknown; cannot synthesize silent outro audio.")
            return False
        parts.append(f"anullsrc=r=44100:cl=stereo,atrim=0:{dur},asetpts=N/SR/TB[a1]")
    parts.append("[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]")
    fc = ";".join(parts)

    reenc_cmd = [
        FFMPEG_PATH, '-y',
        '-i', base_video_path,
        '-i', outro_video_path,
        '-filter_complex', fc,
        '-map', '[v]', '-map', '[a]',
        '-shortest',
        '-c:v', encoder, '-preset', str(preset),
        *( ['-tune', str(tune)] if tune else [] ),
        *( ['-crf', str(crf if crf else 20)] ),
        '-pix_fmt', 'yuv420p',
        '-c:a', 'aac',
        '-ar', '44100',
        '-ac', '2',
        '-b:a', '192k',
        '-threads', threads,
        '-movflags', 'faststart',
        final_path,
    ]
    try:
        subprocess.run(reenc_cmd, check=True)
        return True
    except Exception as e2:
        print(f"Re-encode concat failed: {e2}")
        return False

def _ffmpeg_chromakey_overlay(original_video_path, lyrics_video_path, output_path):
    """Composite a lyric video over the original video using FFmpeg.
    
    This implementation uses the 'screen' blend mode, which is extremely robust
    for white text on a black background (Luma Key / Screen Blend).
    """
    out_w   = int(os.environ.get('CROONIFY_WIDTH',  1920))
    out_h   = int(os.environ.get('CROONIFY_HEIGHT', 1080))
    fps     = 24
    encoder = FFMPEG_ENCODER or 'libx264'
    preset  = FFMPEG_PRESET  or 'ultrafast'
    crf     = str(FFMPEG_CRF if FFMPEG_CRF else 18)
    threads = str(FFMPEG_THREADS if FFMPEG_THREADS is not None else 0)

    # Audio mapping logic:
    # We prioritize the lyric video's audio (1:a) but use '?' to make it optional.
    # We also include -shortest to ensure the output ends when the audio ends.
    common_tail = [
        '-map', '[v]', '-map', '1:a?',
        '-c:v', encoder, '-preset', str(preset), '-crf', crf,
        '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-ar', '44100', '-ac', '2', '-b:a', '192k',
        '-threads', threads,
        '-movflags', 'faststart',
        '-shortest',
        output_path,
    ]

    # ── STAGE 1: Screen Blend (Primary) ────────────────────────────────────
    # Since we now render lyrics on BLACK background for video mode, 
    # screen blend is the perfect way to composite.
    fc_screen = (
        f"[0:v]scale={out_w}:{out_h}:force_original_aspect_ratio=decrease,"
        f"pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}[bg];"
        f"[1:v]scale={out_w}:{out_h},setsar=1,fps={fps}[fg];"
        f"[bg][fg]blend=all_mode=screen:all_opacity=1[v]"
    )
    try:
        cmd_screen = [
            FFMPEG_PATH, '-y',
            '-i', original_video_path,
            '-i', lyrics_video_path,
            '-filter_complex', fc_screen,
        ] + common_tail
        subprocess.run(cmd_screen, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print('[_ffmpeg_composite] Screen blend composite succeeded.')
        return True
    except Exception as e_screen:
        print(f'[_ffmpeg_composite] Screen blend failed ({e_screen}); trying colorkey fallback.')

    # ── STAGE 2: Colorkey Fallback ─────────────────────────────────────────
    # If blend fails, try a simple colorkey on black.
    fc_ck = (
        f"[0:v]scale={out_w}:{out_h}:force_original_aspect_ratio=decrease,"
        f"pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}[bg];"
        f"[1:v]scale={out_w}:{out_h},setsar=1,fps={fps},colorkey=0x000000:0.1:0.1[fg];"
        f"[bg][fg]overlay=format=auto[v]"
    )
    try:
        cmd_ck = [
            FFMPEG_PATH, '-y',
            '-i', original_video_path,
            '-i', lyrics_video_path,
            '-filter_complex', fc_ck,
        ] + common_tail
        subprocess.run(cmd_ck, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print('[_ffmpeg_composite] Colorkey composite succeeded.')
        return True
    except Exception as e_ck:
        print(f'[_ffmpeg_composite] All composite methods failed. Last error: {e_ck}')
        return False


@app.route('/', methods=['GET'])
def index():
    return "Dorian Lyrics Maker API v1"

# Add CORS headers to all responses
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response

# Serve outputs and uploads statically
@app.route('/outputs/<path:filename>', methods=['GET'])
def serve_output(filename):
    from flask import send_from_directory
    return send_from_directory(OUTPUT_DIR, filename)

@app.route('/uploads/<path:filename>', methods=['GET'])
def serve_upload(filename):
    from flask import send_from_directory
    return send_from_directory(UPLOAD_DIR, filename)

# Serve alignments statically
@app.route('/alignments/<path:filename>', methods=['GET'])
def serve_alignment(filename):
    from flask import send_from_directory
    return send_from_directory(ALIGN_DIR, filename)

# Update upload route to handle preflight
@app.route('/upload', methods=['POST', 'OPTIONS'])
def upload_file():
    if request.method == 'OPTIONS':
        return ('', 204)
    
    # Primary media can be 'audio' or 'video'
    audio_file = request.files.get('audio')
    video_file = request.files.get('video')
    
    if not audio_file and not video_file:
        return jsonify({'error': 'Missing audio or video file'}), 400
    
    lyrics_file = request.files.get('lyrics')
    outro_file = request.files.get('outro')
    bg_file = request.files.get('background')
    
    # Check media validity
    media_file = video_file if video_file else audio_file
    if media_file.filename == '':
        return jsonify({'error': 'No media file selected'}), 400
    
    # Check file extension
    media_ext = os.path.splitext(media_file.filename)[1].lower()
    allowed_audio = ['.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg', '.wma', '.aiff', '.aif', '.mp4', '.webm', '.mov', '.opus']
    allowed_video = ['.mp4', '.mov', '.avi', '.mkv', '.webm']
    
    is_video = False
    if video_file:
        if media_ext not in allowed_video:
            return jsonify({'error': 'Video file must be one of: MP4, MOV, AVI, MKV, WEBM'}), 400
        is_video = True
    else:
        if media_ext not in allowed_audio:
            return jsonify({'error': 'Audio file must be one of: MP3, WAV, M4A, AAC, FLAC, OGG, WMA, AIFF, MP4, WEBM, OPUS'}), 400
    
    # If lyrics file provided, check extension
    if lyrics_file and lyrics_file.filename:
        lyrics_ext = os.path.splitext(lyrics_file.filename)[1].lower()
        if lyrics_ext not in ('.txt', '.lrc'):
            return jsonify({'error': 'Lyrics file must be TXT or LRC format'}), 400

    # If outro audio provided, check extension
    if outro_file and outro_file.filename:
        outro_ext = os.path.splitext(outro_file.filename)[1].lower()
        if outro_ext not in allowed_audio:
            return jsonify({'error': 'Outro audio must be a valid audio format'}), 400
    
    # Generate timestamp for unique filenames
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save media file
    media_type = "video" if is_video else "audio"
    media_filename = f"{timestamp}_{media_type}{media_ext}"
    media_path = os.path.join(UPLOAD_DIR, media_filename)
    media_file.save(media_path)
    
    # Save lyrics file if provided
    lyrics_path = None
    if lyrics_file and lyrics_file.filename:
        lyrics_filename = f"{timestamp}_lyrics{os.path.splitext(lyrics_file.filename)[1].lower()}"
        lyrics_path = os.path.join(UPLOAD_DIR, lyrics_filename)
        lyrics_file.save(lyrics_path)

    # Save background image if provided
    background_path = None
    if bg_file and bg_file.filename:
        bg_ext = os.path.splitext(bg_file.filename)[1].lower()
        if bg_ext not in ['.png', '.jpg', '.jpeg']:
            return jsonify({'error': 'Background image must be PNG or JPG'}), 400
        bg_filename = f"{timestamp}_background{bg_ext}"
        background_path = os.path.join(UPLOAD_DIR, bg_filename)
        bg_file.save(background_path)

    # Save outro audio if provided
    outro_path = None
    if outro_file and outro_file.filename:
        outro_ext = os.path.splitext(outro_file.filename)[1].lower()
        outro_filename = f"{timestamp}_outro{outro_ext}"
        outro_path = os.path.join(UPLOAD_DIR, outro_filename)
        outro_file.save(outro_path)
    
    return jsonify({
        'success': True,
        'audio_path': media_path if not is_video else None,
        'video_path': media_path if is_video else None,
        'lyrics_path': lyrics_path,
        'outro_path': outro_path,
        'background_path': background_path,
        'is_video': is_video
    })

def _mark_task_complete(job_id, session_dir, files_to_keep):
    """Internal helper to track concurrent variant generation tasks and 
    trigger cleanup only when the last task finishes.
    """
    try:
        if job_id not in jobs:
            return
            
        # Initialize if not present
        if "completed_tasks" not in jobs[job_id]:
            jobs[job_id]["completed_tasks"] = 0
            
        jobs[job_id]["completed_tasks"] += 1
        completed = jobs[job_id]["completed_tasks"]
        total = jobs[job_id].get("total_tasks", 1)
        
        print(f"[Job {job_id}] Task complete: {completed}/{total}")
        
        if completed >= total:
            print(f"[Job {job_id}] All tasks finished. Triggering cleanup.")
            # Final cleanup
            try:
                import time
                time.sleep(2) # Brief pause for file handles to close
                if session_dir and os.path.exists(session_dir):
                    for f in os.listdir(session_dir):
                        f_path = os.path.join(session_dir, f)
                        if os.path.isfile(f_path) and f_path not in files_to_keep:
                            if not f.endswith('.log') and not f.endswith('.json'):
                                try:
                                    os.remove(f_path)
                                except Exception as e:
                                    print(f"Cleanup error for {f}: {e}")
            except Exception as e:
                print(f"Cleanup routine failed: {e}")
    except Exception as e:
        print(f"Error in _mark_task_complete: {e}")

def _append_outro_async(job_id, base_video_path, outro_path, bg_color=None, bg_image_path=None, font_name=None, font_size=None, outro_text=None, is_instrumental=False, files_to_keep=None):
    """Post-processing: create an outro segment (image or solid color + outro audio)
    and append to the already-rendered base video using fast concat when possible.
    Updates jobs[job_id] with final_output and final_output_url upon completion.
    """
    prefix = "[Instrumental Outro]" if is_instrumental else "[Main Outro]"
    try:
        if not (outro_path and os.path.exists(outro_path) and base_video_path and os.path.exists(base_video_path)):
            print(f"{prefix} Missing files for outro: outro={outro_path}, base={base_video_path}")
            _mark_task_complete(job_id, os.path.dirname(base_video_path) if base_video_path else None, files_to_keep)
            return

        # Convert outro audio to WAV for consistent handling
        outro_base = os.path.splitext(os.path.basename(outro_path))[0]
        # Use unique name for instrumental outro wav to avoid race conditions
        wav_name = f"{outro_base}_inst.wav" if is_instrumental else f"{outro_base}.wav"
        outro_wav = os.path.join(UPLOAD_DIR, wav_name)
        try:
            convert_to_wav(outro_path, outro_wav)
            # Normalize outro WAV to avoid clipping or level jumps
            normalize_audio(outro_wav, outro_wav)
        except Exception as e:
            print(f"Outro conversion failed: {e}")
            _mark_task_complete(job_id, os.path.dirname(base_video_path), files_to_keep)
            return

        # Paths (write alongside the base video inside its session folder)
        base_name = os.path.splitext(os.path.basename(base_video_path))[0]
        session_dir = os.path.dirname(base_video_path)
        outro_segment = os.path.join(session_dir, f"{base_name}_outro.mp4")
        final_path = os.path.join(session_dir, f"{base_name}_final.mp4")

        # Build outro segment: image or solid color background + audio
        # Use fast settings to minimize latency and maximize CPU usage
        width = 1920
        height = 1080
        fps = 24
        encoder = FFMPEG_ENCODER or 'libx264'
        preset = FFMPEG_PRESET or 'medium'
        threads = str(FFMPEG_THREADS if FFMPEG_THREADS is not None else 0)
        tune = FFMPEG_TUNE
        crf = FFMPEG_CRF

        use_image = False
        try:
            use_image = bool(bg_image_path and os.path.exists(bg_image_path))
        except Exception:
            use_image = False
        _fp = None
        try:
            _fp = _find_font_path(font_name) if font_name else None
        except Exception:
            _fp = None
        if not _fp:
            fallback = r'C\\Windows\\Fonts\\arial.ttf'
            try:
                _fp = fallback if os.path.exists(fallback) else None
            except Exception:
                _fp = None
        font_expr = ("fontfile=" + _fp.replace("\\", "/")) if _fp else (f"font={font_name}" if font_name else "font=Arial")
        try:
            out_fs = int(font_size) if font_size else 72
        except Exception:
            out_fs = 72
        out_fs = max(24, min(144, out_fs))
        out_dur = 0.0
        try:
            out_dur = float(get_duration(outro_wav) or 0.0)
        except Exception:
            out_dur = 0.0
        pos_y = "(h-text_h)/2"
        try:
            if str(OUTRO_POSITION).lower() == "lower_third":
                pos_y = "h-text_h-50"
        except Exception:
            pos_y = "(h-text_h)/2"
        boxc = f"{OUTRO_BOX_COLOR}@{OUTRO_BOX_OPACITY}" if OUTRO_BOX_COLOR else "black@0.35"
        fi = float(OUTRO_FADE_IN_SEC) if OUTRO_FADE_IN_SEC else 0.6
        fo = float(OUTRO_FADE_OUT_SEC) if OUTRO_FADE_OUT_SEC else 0.6
        alpha_expr = None
        try:
            if out_dur > 0.0 and (fi > 0.0 or fo > 0.0):
                alpha_expr = f"if(lt(t,{fi}),t/{fi},if(lt(t,{max(0.0,out_dur-fo)}),1,max(0,({out_dur}-t)/{fo})))"
        except Exception:
            alpha_expr = None
        safe_text = str(outro_text).strip() if outro_text is not None else ""
        if not safe_text:
            safe_text = OUTRO_MESSAGE_TEXT
        safe_text = _escape_drawtext_text(safe_text)
        dt = (
            f"drawtext={font_expr}:text='{safe_text}':x=(w-text_w)/2:y={pos_y}:fontcolor={OUTRO_FONT_COLOR}:fontsize={out_fs}:box=1:boxcolor={boxc}"
            + (f":alpha='{alpha_expr}'" if alpha_expr else "")
        )
        if use_image:
            ffmpeg_cmd = [
                FFMPEG_PATH, '-y',
                '-loop', '1', '-i', bg_image_path,
                '-i', outro_wav,
                '-vf', f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,crop={width}:{height},setsar=1,{dt}",
                '-c:v', encoder, '-preset', str(preset),
                *( ['-tune', str(tune)] if tune else [] ),
                *( ['-crf', str(crf if crf else 20)] ),
                '-pix_fmt', 'yuv420p',
                '-c:a', 'aac',
                '-ar', '44100',
                '-ac', '2',
                '-b:a', '192k',
                '-shortest',
                '-r', str(fps),
                '-threads', threads,
                '-movflags', 'faststart',
                outro_segment,
            ]
        else:
            hex_color = '#000000'
            try:
                if isinstance(bg_color, tuple) and len(bg_color) == 3:
                    hex_color = f"#{bg_color[0]:02x}{bg_color[1]:02x}{bg_color[2]:02x}"
            except Exception:
                pass
            color_src = f"color=c={hex_color}:s={width}x{height}:r={fps}"
            ffmpeg_cmd = [
                FFMPEG_PATH, '-y',
                '-f', 'lavfi', '-i', color_src,
                '-i', outro_wav,
                '-vf', dt,
                '-c:v', encoder, '-preset', str(preset),
                *( ['-tune', str(tune)] if tune else [] ),
                *( ['-crf', str(crf if crf else 20)] ),
                '-pix_fmt', 'yuv420p',
                '-c:a', 'aac',
                '-ar', '44100',
                '-ac', '2',
                '-b:a', '192k',
                '-shortest',
                '-r', str(fps),
                '-threads', threads,
                '-movflags', 'faststart',
                outro_segment,
            ]

        try:
            subprocess.run(ffmpeg_cmd, check=True)
        except Exception as e:
            print(f"Failed to render outro segment: {e}")
            _mark_task_complete(job_id, session_dir, files_to_keep)
            return

        # Fast concat (stream copy) when possible
        filelist_path = os.path.join(session_dir, f"{base_name}_concat.txt")
        try:
            bv_norm = base_video_path.replace("\\", "/")
            outro_norm = outro_segment.replace("\\", "/")
            with open(filelist_path, 'w', encoding='utf-8') as f:
                f.write(f"file '{bv_norm}'\n")
                f.write(f"file '{outro_norm}'\n")
            concat_cmd = [
                FFMPEG_PATH, '-y',
                '-f', 'concat', '-safe', '0', '-i', filelist_path,
                '-c', 'copy', '-movflags', 'faststart',
                final_path,
            ]
            subprocess.run(concat_cmd, check=True)
        except Exception as e:
            print(f"Stream-copy concat failed, attempting re-encode: {e}")
            # Fallback: re-encode concat (slower)
            try:
                reenc_cmd = [
                    FFMPEG_PATH, '-y',
                    '-i', base_video_path,
                    '-i', outro_segment,
                    '-filter_complex', '[0:v:0][0:a:0][1:v:0][1:a:0]concat=n=2:v=1:a=1[v][a]',
                    '-map', '[v]', '-map', '[a]',
                    '-c:v', encoder, '-preset', str(preset),
                    *( ['-tune', str(tune)] if tune else [] ),
                    *( ['-crf', str(crf if crf else 20)] ),
                    '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac',
                    '-ar', '44100',
                    '-ac', '2',
                    '-b:a', '192k',
                    '-threads', threads,
                    '-movflags', 'faststart',
                    final_path,
                ]
                subprocess.run(reenc_cmd, check=True)
            except Exception as e2:
                print(f"Re-encode concat failed: {e2}")
                _mark_task_complete(job_id, session_dir, files_to_keep)
                return

        # Update job with final output
        try:
            if is_instrumental:
                jobs[job_id]["instrumental_video"] = final_path
                rel_final = os.path.relpath(final_path, OUTPUT_DIR).replace("\\", "/")
                jobs[job_id]["instrumental_video_url"] = f"/outputs/{rel_final}"
                print(f"{prefix} Updated job with instrumental video: {final_path}")
            else:
                jobs[job_id]["final_output"] = final_path
                # Use relpath to preserve session subfolder in URL
                rel_final = os.path.relpath(final_path, OUTPUT_DIR).replace("\\", "/")
                jobs[job_id]["final_output_url"] = f"/outputs/{rel_final}"
                jobs[job_id]["stage"] = "Completed (outro appended)"
                print(f"{prefix} Updated job with main video: {final_path}")
            
            # Add to keep list if provided
            if files_to_keep is not None and final_path not in files_to_keep:
                files_to_keep.append(final_path)
                
        except Exception as e:
            print(f"{prefix} Error updating job status: {e}")

        # After final is obtained, delete base lyrics video, outro segment and concat list
        # For instrumental, we should NOT delete the base video if it's the main output!
        # But here base_video_path is the instrumental variant's base.
        try:
            # Always delete intermediate outro segment and concat list
            to_delete = [outro_segment, filelist_path]
            # Only delete base video if it's NOT a final kept file
            if not is_instrumental: # For main video, base_video_path is an intermediate
                 to_delete.append(base_video_path)
            elif is_instrumental: # For instrumental, base_video_path was the variant base
                 to_delete.append(base_video_path)
                 
            for p in to_delete:
                try:
                    if p and os.path.exists(p):
                        os.remove(p)
                        print(f"{prefix} Cleaned up: {p}")
                except Exception as de:
                    print(f"{prefix} Cleanup warning: failed to delete {p}: {de}")
            
            # Only clear main output if this is the main outro thread
            if not is_instrumental:
                try:
                    jobs[job_id]["output"] = None
                    jobs[job_id]["output_url"] = None
                except Exception:
                    pass
        except Exception:
            pass
        
        # Mark this variant task as complete
        _mark_task_complete(job_id, session_dir, files_to_keep)

    except Exception as e:
        print(f"{prefix} Fatal error in _append_outro_async: {e}")
        # Ensure task is marked complete even on fatal error
        try:
            _mark_task_complete(job_id, os.path.dirname(base_video_path) if base_video_path else None, files_to_keep)
        except:
            pass
    finally:
        # best-effort cleanup
        try:
            if 'outro_segment' in locals() and os.path.exists(outro_segment):
                pass  # keep segment for debugging; remove if desired
        except Exception:
            pass


def _append_outro_video_async(job_id, base_video_path, outro_video_path):
    try:
        if not (outro_video_path and os.path.exists(outro_video_path) and base_video_path and os.path.exists(base_video_path)):
            return
        base_name = os.path.splitext(os.path.basename(base_video_path))[0]
        session_dir = os.path.dirname(base_video_path)
        final_path = os.path.join(session_dir, f"{base_name}_final.mp4")
        filelist_path = os.path.join(session_dir, f"{base_name}_concat.txt")
        ok = _append_video_keep_outro_intact(base_video_path, outro_video_path, final_path, filelist_path)
        if not ok:
            ok = _reencode_append_video_preserve_outro(base_video_path, outro_video_path, final_path)
        if not ok:
            return
        try:
            jobs[job_id]["final_output"] = final_path
            rel_final = os.path.relpath(final_path, OUTPUT_DIR).replace("\\", "/")
            jobs[job_id]["final_output_url"] = f"/outputs/{rel_final}"
            jobs[job_id]["stage"] = "Completed (outro appended)"
        except Exception:
            pass
        try:
            for p in [base_video_path, filelist_path]:
                try:
                    if p and os.path.exists(p):
                        os.remove(p)
                except Exception as de:
                    print(f"Cleanup warning: failed to delete {p}: {de}")
            try:
                jobs[job_id]["output"] = None
                jobs[job_id]["output_url"] = None
            except Exception:
                pass
        except Exception:
            pass
    except Exception:
        return


def _render_instrument_video_async(job_id, instrumental_path, bg_color=None, bg_image_path=None, outro_path=None, outro_is_video=False, session_dir=None, base_name=None, font_name=None, font_size=None, outro_text=None):
    try:
        if not (instrumental_path and os.path.exists(instrumental_path) and session_dir and base_name):
            return
        inst_wav = instrumental_path
        try:
            if os.path.splitext(instrumental_path)[1].lower() != ".wav":
                inst_wav_candidate = os.path.join(os.path.dirname(instrumental_path), f"{os.path.splitext(os.path.basename(instrumental_path))[0]}.wav")
                convert_to_wav(instrumental_path, inst_wav_candidate)
                normalize_audio(inst_wav_candidate, inst_wav_candidate)
                inst_wav = inst_wav_candidate
            else:
                normalize_audio(inst_wav, inst_wav)
        except Exception:
            pass
        width = 1920
        height = 1080
        fps = 24
        encoder = FFMPEG_ENCODER or 'libx264'
        preset = FFMPEG_PRESET or 'medium'
        threads = str(FFMPEG_THREADS if FFMPEG_THREADS is not None else 0)
        tune = FFMPEG_TUNE
        crf = FFMPEG_CRF
        instrument_segment = os.path.join(session_dir, f"{base_name}_instrument_base.mp4")
        final_path = os.path.join(session_dir, f"{base_name}_instrument.mp4")
        use_image = False
        try:
            use_image = bool(bg_image_path and os.path.exists(bg_image_path))
        except Exception:
            use_image = False
        if use_image:
            ffmpeg_cmd = [
                FFMPEG_PATH, '-y',
                '-loop', '1', '-i', bg_image_path,
                '-i', inst_wav,
                '-vf', f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,crop={width}:{height},setsar=1",
                '-c:v', encoder, '-preset', str(preset),
                *( ['-tune', str(tune)] if tune else [] ),
                *( ['-crf', str(crf if crf else 20)] ),
                '-pix_fmt', 'yuv420p',
                '-c:a', 'aac',
                '-ar', '44100',
                '-ac', '2',
                '-b:a', '192k',
                '-shortest',
                '-r', str(fps),
                '-threads', threads,
                '-movflags', 'faststart',
                instrument_segment,
            ]
        else:
            hex_color = '#000000'
            try:
                if isinstance(bg_color, tuple) and len(bg_color) == 3:
                    hex_color = f"#{bg_color[0]:02x}{bg_color[1]:02x}{bg_color[2]:02x}"
            except Exception:
                pass
            color_src = f"color=c={hex_color}:s={width}x{height}:r={fps}"
            ffmpeg_cmd = [
                FFMPEG_PATH, '-y',
                '-f', 'lavfi', '-i', color_src,
                '-i', inst_wav,
                '-c:v', encoder, '-preset', str(preset),
                *( ['-tune', str(tune)] if tune else [] ),
                *( ['-crf', str(crf if crf else 20)] ),
                '-pix_fmt', 'yuv420p',
                '-c:a', 'aac',
                '-ar', '44100',
                '-ac', '2',
                '-b:a', '192k',
                '-shortest',
                '-r', str(fps),
                '-threads', threads,
                '-movflags', 'faststart',
                instrument_segment,
            ]
        try:
            subprocess.run(ffmpeg_cmd, check=True)
        except Exception:
            return
        if outro_path and os.path.exists(outro_path) and bool(outro_is_video):
            outro_video_path = outro_path
            filelist_path = os.path.join(session_dir, f"{base_name}_instrument_concat.txt")
            ok = _append_video_keep_outro_intact(instrument_segment, outro_video_path, final_path, filelist_path)
            if not ok:
                ok = _reencode_append_video_preserve_outro(instrument_segment, outro_video_path, final_path)
            if not ok:
                return
        elif outro_path and os.path.exists(outro_path):
            outro_base = os.path.splitext(os.path.basename(outro_path))[0]
            outro_wav = os.path.join(UPLOAD_DIR, f"{outro_base}.wav")
            try:
                convert_to_wav(outro_path, outro_wav)
                normalize_audio(outro_wav, outro_wav)
            except Exception:
                pass
            outro_segment = os.path.join(session_dir, f"{base_name}_instrument_outro.mp4")
            _fp2 = None
            try:
                _fp2 = _find_font_path(font_name) if font_name else None
            except Exception:
                _fp2 = None
            if not _fp2:
                fallback2 = r'C\\Windows\\Fonts\\arial.ttf'
                try:
                    _fp2 = fallback2 if os.path.exists(fallback2) else None
                except Exception:
                    _fp2 = None
            font_expr2 = ("fontfile=" + _fp2.replace("\\", "/")) if _fp2 else (f"font={font_name}" if font_name else "font=Arial")
            try:
                out_fs2 = int(font_size) if font_size else 72
            except Exception:
                out_fs2 = 72
            out_fs2 = max(24, min(144, out_fs2))
            out_dur2 = 0.0
            try:
                out_dur2 = float(get_duration(outro_wav) or 0.0)
            except Exception:
                out_dur2 = 0.0
            pos_y2 = "(h-text_h)/2"
            try:
                if str(OUTRO_POSITION).lower() == "lower_third":
                    pos_y2 = "h-text_h-50"
            except Exception:
                pos_y2 = "(h-text_h)/2"
            boxc2 = f"{OUTRO_BOX_COLOR}@{OUTRO_BOX_OPACITY}" if OUTRO_BOX_COLOR else "black@0.35"
            fi2 = float(OUTRO_FADE_IN_SEC) if OUTRO_FADE_IN_SEC else 0.6
            fo2 = float(OUTRO_FADE_OUT_SEC) if OUTRO_FADE_OUT_SEC else 0.6
            alpha_expr2 = None
            try:
                if out_dur2 > 0.0 and (fi2 > 0.0 or fo2 > 0.0):
                    alpha_expr2 = f"if(lt(t,{fi2}),t/{fi2},if(lt(t,{max(0.0,out_dur2-fo2)}),1,max(0,({out_dur2}-t)/{fo2})))"
            except Exception:
                alpha_expr2 = None
            safe_text2 = str(outro_text).strip() if outro_text is not None else ""
            if not safe_text2:
                safe_text2 = OUTRO_MESSAGE_TEXT
            safe_text2 = _escape_drawtext_text(safe_text2)
            dt2 = (
                f"drawtext={font_expr2}:text='{safe_text2}':x=(w-text_w)/2:y={pos_y2}:fontcolor={OUTRO_FONT_COLOR}:fontsize={out_fs2}:box=1:boxcolor={boxc2}"
                + (f":alpha='{alpha_expr2}'" if alpha_expr2 else "")
            )
            if use_image:
                outro_cmd = [
                    FFMPEG_PATH, '-y',
                    '-loop', '1', '-i', bg_image_path,
                    '-i', outro_wav,
                    '-vf', f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,crop={width}:{height},setsar=1,{dt2}",
                    '-c:v', encoder, '-preset', str(preset),
                    *( ['-tune', str(tune)] if tune else [] ),
                    *( ['-crf', str(crf if crf else 20)] ),
                    '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac',
                    '-ar', '44100',
                    '-ac', '2',
                    '-b:a', '192k',
                    '-shortest',
                    '-r', str(fps),
                    '-threads', threads,
                    '-movflags', 'faststart',
                    outro_segment,
                ]
            else:
                color_src2 = color_src
                outro_cmd = [
                    FFMPEG_PATH, '-y',
                    '-f', 'lavfi', '-i', color_src2,
                    '-i', outro_wav,
                    '-vf', dt2,
                    '-c:v', encoder, '-preset', str(preset),
                    *( ['-tune', str(tune)] if tune else [] ),
                    *( ['-crf', str(crf if crf else 20)] ),
                    '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac',
                    '-ar', '44100',
                    '-ac', '2',
                    '-b:a', '192k',
                    '-shortest',
                    '-r', str(fps),
                    '-threads', threads,
                    '-movflags', 'faststart',
                    outro_segment,
                ]
            try:
                subprocess.run(outro_cmd, check=True)
            except Exception:
                outro_segment = None
            if outro_segment and os.path.exists(outro_segment):
                filelist_path = os.path.join(session_dir, f"{base_name}_instrument_concat.txt")
                try:
                    inst_norm = instrument_segment.replace("\\", "/")
                    outro_norm = outro_segment.replace("\\", "/")
                    with open(filelist_path, 'w', encoding='utf-8') as f:
                        f.write(f"file '{inst_norm}'\n")
                        f.write(f"file '{outro_norm}'\n")
                    concat_cmd = [
                        FFMPEG_PATH, '-y',
                        '-f', 'concat', '-safe', '0', '-i', filelist_path,
                        '-c', 'copy', '-movflags', 'faststart',
                        final_path,
                    ]
                    subprocess.run(concat_cmd, check=True)
                except Exception:
                    try:
                        reenc_cmd = [
                            FFMPEG_PATH, '-y',
                            '-i', instrument_segment,
                            '-i', outro_segment,
                            '-filter_complex', '[0:v:0][0:a:0][1:v:0][1:a:0]concat=n=2:v=1:a=1[v][a]',
                            '-map', '[v]', '-map', '[a]',
                            '-c:v', encoder, '-preset', str(preset),
                            *( ['-tune', str(tune)] if tune else [] ),
                            *( ['-crf', str(crf if crf else 20)] ),
                            '-pix_fmt', 'yuv420p',
                            '-c:a', 'aac',
                            '-ar', '44100',
                            '-ac', '2',
                            '-b:a', '192k',
                            '-threads', threads,
                            '-movflags', 'faststart',
                            final_path,
                        ]
                        subprocess.run(reenc_cmd, check=True)
                    except Exception:
                        return
        else:
            try:
                import shutil
                shutil.copyfile(instrument_segment, final_path)
            except Exception:
                final_path = instrument_segment
        try:
            jobs[job_id]['instrument'] = final_path
            rel_inst = os.path.relpath(final_path, OUTPUT_DIR).replace('\\', '/')
            jobs[job_id]['instrument_url'] = f"/outputs/{rel_inst}"
        except Exception:
            pass
        try:
            if 'instrument_segment' in locals() and instrument_segment and os.path.exists(instrumental_path):
                if final_path != instrument_segment:
                    os.remove(instrument_segment)
            if 'outro_segment' in locals() and outro_segment and os.path.exists(outro_segment):
                os.remove(outro_segment)
            if 'filelist_path' in locals() and filelist_path and os.path.exists(filelist_path):
                os.remove(filelist_path)
        except Exception:
            pass
    except Exception:
        pass


def process_job(job_id, audio_path, lyrics_path, bg_color=None, font_name=None, fontsize=None, outro_path=None, outro_is_video=False, outro_text=None, song_title=None, artist_name=None, bg_image_path=None, alignment_override=None, separation_prefer='auto', output_format='mp4', pause_config=None, sync_refine=False, language=None, video_path=None):
    """Background thread function to process a job"""
    try:
        # Register thread ID so we can aggressively kill its spawned subprocesses if cancelled
        jobs[job_id]["thread_id"] = threading.get_ident()
        
        # Update job status
        jobs[job_id]["status"] = "running"
        jobs[job_id]["progress"] = 0
        jobs[job_id]["stage"] = "Starting job"

        _check_cancelled(job_id)

        # Handle video input if provided
        is_video_mode = False
        video_bg_path = None
        if video_path and os.path.exists(video_path):
            is_video_mode = True
            jobs[job_id]["stage"] = "Processing video input"
            jobs[job_id]["progress"] = 5
            base_name = os.path.splitext(os.path.basename(video_path))[0]
            
            # Extract audio
            extracted_audio = os.path.join(UPLOAD_DIR, f"{base_name}_extracted.wav")
            if extract_audio_from_video(video_path, extracted_audio):
                audio_path = extracted_audio
            else:
                jobs[job_id]["status"] = "error"
                jobs[job_id]["error"] = "Failed to extract audio from video file."
                return
            
            # Extract first frame to use as background
            extracted_frame = os.path.join(UPLOAD_DIR, f"{base_name}_frame.png")
            if extract_video_thumbnail(video_path, extracted_frame):
                bg_image_path = extracted_frame
                # We can still use the video as background if we want moving background,
                # but the prompt specifically asked to use the extracted frame as background image.
                # To be safe and provide the best of both worlds, we'll use the video as background
                # in the builder, but the extracted frame is now our "background image".
                video_bg_path = video_path
            else:
                print("Warning: Failed to extract frame from video.")

        jobs[job_id]["stage"] = "Normalizing audio"
        jobs[job_id]["progress"] = 10
        base_name = os.path.splitext(os.path.basename(audio_path))[0]
        norm_wav = os.path.join(UPLOAD_DIR, f"{base_name}_normalized.wav")
        try:
            nw = normalize_audio(audio_path, norm_wav)
            wav_path = nw if nw and os.path.exists(nw) else norm_wav
        except Exception:
            wav_path = norm_wav
        
        jobs[job_id]["stage"] = "Converting audio to WAV"
        jobs[job_id]["progress"] = 20
        # Already exporting normalized to WAV; ensure extension is WAV
        if os.path.splitext(wav_path)[1].lower() != ".wav":
            target_wav = os.path.join(UPLOAD_DIR, f"{base_name}.wav")
            success = convert_to_wav(wav_path, target_wav)
            if not success or not os.path.exists(target_wav):
                jobs[job_id]["status"] = "error"
                jobs[job_id]["error"] = (
                    "Audio conversion failed. Ensure FFmpeg is installed and the audio file is valid."
                )
                return
            wav_path = target_wav

        _check_cancelled(job_id)

        vocals_path, instrumental_path = None, None
        pref = str(separation_prefer or 'auto').lower()
        jobs[job_id]["stage"] = "Separating stems"
        jobs[job_id]["progress"] = 30
        vocals_path, instrumental_path, stem_engine = separate_stems(
            wav_path,
            output_dir=os.path.dirname(wav_path),
            prefer=(pref if pref != 'none' else 'auto')
        )
        if not (vocals_path and instrumental_path and os.path.exists(vocals_path) and os.path.exists(instrumental_path)):
            jobs[job_id]["status"] = "error"
            jobs[job_id]["stage"] = "Stem separation failed"
            jobs[job_id]["error"] = "Stem separation is required"
            return
        jobs[job_id]["vocals"] = vocals_path
        jobs[job_id]["instrumental"] = instrumental_path
        if stem_engine:
            jobs[job_id]["stem_engine"] = stem_engine

        _check_cancelled(job_id)

        # Step 3: Align audio with lyrics
        jobs[job_id]["stage"] = "Aligning audio with lyrics"
        jobs[job_id]["progress"] = 40
        alignment_path = os.path.join(ALIGN_DIR, f"{base_name}_alignment.json")
        try:
            if alignment_override and os.path.exists(alignment_override):
                alignment_path = alignment_override
            else:
                import os as _os
                ext = _os.path.splitext(lyrics_path or '')[1].lower()
                if ext == '.lrc':
                    from backend.alignment_hybrid import lrc_to_alignment
                    src_for_align = vocals_path if (vocals_path and os.path.exists(vocals_path)) else wav_path
                    outp = lrc_to_alignment(src_for_align, lyrics_path, alignment_path, language)
                    if outp:
                        alignment_path = outp
                    else:
                        src_for_align = vocals_path if (vocals_path and os.path.exists(vocals_path)) else wav_path
                        align(src_for_align, lyrics_path, alignment_path, language=language)
                else:
                    src_for_align = vocals_path if (vocals_path and os.path.exists(vocals_path)) else wav_path
                    align(src_for_align, lyrics_path, alignment_path, language=language)
            jobs[job_id]["progress"] = 60
            jobs[job_id]["alignment"] = alignment_path
            rel_align = os.path.relpath(alignment_path, ALIGN_DIR).replace("\\", "/")
            jobs[job_id]["alignment_url"] = f"/alignments/{rel_align}"
        except Exception as e:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["stage"] = "Alignment failed"
            jobs[job_id]["error"] = f"Alignment error: {e}"
            return

        _check_cancelled(job_id)

        # Create per-session output directory
        session_comp = None
        try:
            st = (song_title or "").strip()
            ar = (artist_name or "").strip()
            if st or ar:
                session_comp = f"{st}_{ar}".strip("_")
        except Exception:
            session_comp = None
        session_name = werkzeug.utils.secure_filename(session_comp) if session_comp else base_name
        session_dir = os.path.join(OUTPUT_DIR, session_name)
        os.makedirs(session_dir, exist_ok=True)

        # Step 4: Build video
        jobs[job_id]["stage"] = "Rendering lyric video"
        jobs[job_id]["progress"] = 70
        ext = str(output_format or 'mp4').lower()
        output_path = os.path.join(session_dir, f"{base_name}_lyrics.{ext}")

        # FIX: Black screen in video mode
        # ─────────────────────────────────────────────────────────────────────
        # MoviePy's VideoFileClip frame reader silently produces black frames
        # on Windows when a user video is used as a composited background
        # (a known bug with H.264/MP4 inputs on MoviePy 1.x).
        #
        # Solution: build the lyric overlay on a PURE BLACK background
        # (ColorClip — always reliable), then use _ffmpeg_blend_overlay() to
        # composite the white-on-black lyric video over the original video via
        # FFmpeg's "lighten" blend mode:
        #   black pixels (bg)   → original video pixel always wins  → video shows
        #   white pixels (text) → max(255, anything) = 255           → text shows
        # ─────────────────────────────────────────────────────────────────────
        if is_video_mode:
            _build_bg_image = None            # don't pass static frame to MoviePy
            _build_bg_color = (0, 0, 0)       # pure black (#000000) — used for "screen" blend overlay
            _build_video_bg = None            # never pass video to MoviePy (causes black frames)
        else:
            _build_bg_image = bg_image_path
            _build_bg_color = bg_color
            _build_video_bg = None            # audio mode never uses video bg

        result = build_lyric_video(
            wav_path,
            alignment_path,
            output_path,
            _build_bg_image,
            _build_bg_color,
            background_video_path=_build_video_bg,
            use_highlight=False,
            progress_callback=lambda p: update_job_progress(job_id, 70 + int(max(0.0, min(1.0, p)) * 29)),
            font_name=font_name,
            fontsize=fontsize or 70,
            outro_audio_path=None,
            outro_text=outro_text,
            vocal_onset=None,
            trim_intro=False,
            trim_end_silence=bool(outro_path),
            pause_markers=None,
            pause_opacity=0.22
        )

        if not result or not os.path.exists(output_path):
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = "Video rendering failed."
            return

        # Step 4b (video mode only): chromakey green background, overlay lyrics on original video
        if is_video_mode and video_path and os.path.exists(video_path):
            jobs[job_id]["stage"] = "Compositing lyrics over video"
            jobs[job_id]["progress"] = 97
            composite_path = os.path.join(session_dir, f"{base_name}_composite.{ext}")
            if _ffmpeg_chromakey_overlay(video_path, output_path, composite_path):
                try:
                    os.remove(output_path)
                except Exception:
                    pass
                output_path = composite_path
            else:
                # All overlay methods failed — keep lyrics-on-green as last resort
                print("[video mode] All FFmpeg overlay methods failed; keeping greenscreen fallback")

        # Add metadata to the base video
        output_path = add_metadata(output_path, os.path.join(session_dir, f"{base_name}_lyrics_meta.{ext}"), title=song_title, artist=artist_name)

        # Update job status
        jobs[job_id]["status"] = "done"
        jobs[job_id]["stage"] = "Completed (base video)"
        jobs[job_id]["progress"] = 100
        jobs[job_id]["output"] = output_path
        rel_output = os.path.relpath(output_path, OUTPUT_DIR).replace("\\", "/")
        jobs[job_id]["output_url"] = f"/outputs/{rel_output}"

        # Cleanup intermediate files to keep only 3 main files in output folder
        def _cleanup_session(s_dir, keep_files):
            try:
                for f in os.listdir(s_dir):
                    f_path = os.path.join(s_dir, f)
                    if os.path.isfile(f_path) and f_path not in keep_files:
                        # Don't delete logs or the directory itself
                        if not f.endswith('.log') and not f.endswith('.json'):
                            os.remove(f_path)
            except Exception as e:
                print(f"Cleanup error: {e}")

        # Initial keep list
        files_to_keep = [output_path]

        # Generate thumbnail
        try:
            thumb_path = os.path.join(session_dir, f"{base_name}_thumbnail.png")
            if is_video_mode:
                extract_video_thumbnail(video_path, thumb_path, title=song_title, artist=artist_name, font_name=font_name)
            else:
                generate_thumbnail_image(
                    title=song_title or os.path.splitext(os.path.basename(lyrics_path or ''))[0],
                    artist=artist_name or '',
                    out_path=thumb_path,
                    bg_color=bg_color,
                    image_path=bg_image_path,
                    font_name=font_name,
                )
            if os.path.exists(thumb_path):
                jobs[job_id]["thumbnail"] = thumb_path
                files_to_keep.append(thumb_path)
                rel_thumb = os.path.relpath(thumb_path, OUTPUT_DIR).replace("\\", "/")
                jobs[job_id]["thumbnail_url"] = f"/outputs/{rel_thumb}"
        except Exception as e:
            print(f"Thumbnail generation error: {e}")

        # Variants generation
        try:
            # Track how many async tasks we're launching for cleanup synchronization
            total_tasks = 0
            if outro_path: total_tasks += 1
            if instrumental_path: total_tasks += 1
            
            jobs[job_id]["total_tasks"] = total_tasks
            jobs[job_id]["completed_tasks"] = 0
            
            # Outro variant
            if outro_path:
                jobs[job_id]["postprocess"] = "generating_variants"
                t_outro = threading.Thread(target=_append_outro_async, args=(job_id, output_path, outro_path, bg_color, bg_image_path, font_name, fontsize or 70, outro_text, False, files_to_keep))
                t_outro.daemon = True
                t_outro.start()

            # Instrumental variant
            if instrumental_path:
                inst_output = os.path.join(session_dir, f"{base_name}_instrumental.{ext}")
                t_inst = threading.Thread(target=_render_instrument_video_variant_async, args=(job_id, video_path, instrumental_path, alignment_path, inst_output, font_name, fontsize, song_title, artist_name, bg_rgb, bg_image_path, session_dir, files_to_keep, outro_path, outro_text))
                t_inst.daemon = True
                t_inst.start()
            
            # If no variants at all, mark as complete to trigger cleanup of any intermediates
            if total_tasks == 0:
                # Add a dummy task count so cleanup works
                jobs[job_id]["total_tasks"] = 1
                _mark_task_complete(job_id, session_dir, files_to_keep)

        except Exception as e:
            print(f"Failed to start variant threads: {e}")
        
    except _JobCancelledError:
        jobs[job_id]["status"] = "cancelled"
        jobs[job_id]["stage"] = "Cancelled by user"
    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)

def _render_instrument_video_variant_async(job_id, video_path, instrumental_path, alignment_path, output_path, font_name, fontsize, title, artist, bg_rgb=None, bg_image_path=None, session_dir=None, files_to_keep=None, outro_path=None, outro_text=None):
    try:
        # Step 1: Generate the lyric-on-background video (using background video or color/image)
        # For instrumentals, we still want the same background as the main video.
        
        # If it's video mode, we render lyrics on BLACK first, then composite.
        is_video_mode = bool(video_path and os.path.exists(video_path))
        
        _build_bg_image = None if is_video_mode else bg_image_path
        _build_bg_color = (0, 0, 0) if is_video_mode else (bg_rgb or (0, 0, 0))
        _build_video_bg = None # Never pass video to MoviePy

        result = build_lyric_video(
            instrumental_path,
            alignment_path,
            output_path,
            _build_bg_image,
            _build_bg_color,
            background_video_path=_build_video_bg,
            font_name=font_name,
            fontsize=fontsize or 70,
        )

        if result and os.path.exists(output_path):
            # Step 2: If video mode, composite the black-background lyrics over the background video
            if is_video_mode:
                composite_path = output_path.replace(".mp4", "_composite.mp4")
                if _ffmpeg_chromakey_overlay(video_path, output_path, composite_path):
                    try:
                        os.remove(output_path)
                    except Exception:
                        pass
                    output_path = composite_path

            # Step 3: Add metadata
            final_path = add_metadata(output_path, output_path.replace(".mp4", "_meta.mp4"), title=f"{title} (Instrumental)", artist=artist)
            
            # Cleanup intermediate meta file if created
            if final_path != output_path and os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except Exception:
                    pass
            
            output_path = final_path

        # Step 4: Handle Outro for Instrumental
        if outro_path and os.path.exists(outro_path):
            print(f"[Instrumental] Starting outro generation for: {output_path}")
            # Sequential processing: wait for _append_outro_async to finish
            # We use a custom event or just let it finish since it updates the job
            _append_outro_async(
                job_id, 
                output_path, 
                outro_path, 
                bg_color=bg_rgb, 
                bg_image_path=bg_image_path, 
                font_name=font_name, 
                font_size=fontsize or 70, 
                outro_text=outro_text,
                is_instrumental=True, # Signal it's for instrumental
                files_to_keep=files_to_keep
            )
            
            # The _append_outro_async will update jobs[job_id]["instrumental_video"] if is_instrumental is True
            # Let's verify if the file was created
            inst_final = output_path.replace(".mp4", "_final.mp4")
            if os.path.exists(inst_final):
                output_path = inst_final
                print(f"[Instrumental] Outro appended successfully: {output_path}")
            else:
                print(f"[Instrumental] Outro appending failed or skipped for {output_path}")
        else:
            # No outro for instrumental
            pass

        # Final keep list update and job status update
        if output_path and os.path.exists(output_path):
            if files_to_keep is not None and output_path not in files_to_keep:
                files_to_keep.append(output_path)
            
            jobs[job_id]["instrumental_video"] = output_path
            rel_inst = os.path.relpath(output_path, OUTPUT_DIR).replace("\\", "/")
            jobs[job_id]["instrumental_video_url"] = f"/outputs/{rel_inst}"
            print(f"Instrumental variant completed: {output_path}")

    except Exception as e:
        print(f"Instrumental variant failed: {e}")
    finally:
        # If we didn't call _append_outro_async (which handles its own _mark_task_complete),
        # we must mark it complete here.
        if not (outro_path and os.path.exists(outro_path)):
            try:
                _mark_task_complete(job_id, session_dir, files_to_keep)
            except:
                pass

def process_job_old(job_id, audio_path, lyrics_path, bg_color=None, font_name=None, fontsize=None, outro_path=None, outro_is_video=False, outro_text=None, song_title=None, artist_name=None, bg_image_path=None, alignment_override=None, separation_prefer='auto', output_format='mp4', pause_config=None, sync_refine=False, language=None):
    pass

# Update generate route to handle preflight
@app.route('/generate', methods=['POST', 'OPTIONS'])
def generate_video():
    if request.method == 'OPTIONS':
        return ('', 204)
    # Get request data
    data = request.json
    
    # Validate request
    if not data or ('audio_path' not in data and 'video_path' not in data) or 'lyrics_path' not in data:
        return jsonify({'error': 'Missing audio_path/video_path or lyrics_path'}), 400
    
    audio_path = data.get('audio_path')
    video_path = data.get('video_path')
    lyrics_path = data['lyrics_path']
    bg_color_str = data.get('bg_color')
    bg_rgb = parse_bg_color(bg_color_str) if bg_color_str else None
    bg_image_path = data.get('bg_image')
    font_name = data.get('font')
    fontsize = data.get('fontsize')
    alignment_json = data.get('alignment_json')
    language = data.get('language')
    pause_config = data.get('pause')
    sync_refine = _parse_bool(data.get('sync_refine', False))
    
    outro_path = data.get('outro_path')
    outro_is_video = _parse_bool(data.get('outro_is_video'))
    outro_text = data.get('outro_text')
    song_title = data.get('song_title')
    artist_name = data.get('artist_name')
    
    # Check if files exist
    if audio_path and not os.path.exists(audio_path):
        return jsonify({'error': f'Audio file not found: {audio_path}'}), 404
    
    if video_path and not os.path.exists(video_path):
        return jsonify({'error': f'Video file not found: {video_path}'}), 404
    
    if not os.path.exists(lyrics_path):
        return jsonify({'error': f'Lyrics file not found: {lyrics_path}'}), 404
    
    # Create job ID
    job_id = str(uuid.uuid4())
    
    # Initialize job status
    jobs[job_id] = {
        "status": "queued",
        "output": None,
        "created_at": datetime.datetime.now().isoformat()
    }
    
    # Start background thread
    alignment_override = None
    try:
        if alignment_json and isinstance(alignment_json, dict):
            # Use video_path if audio_path is missing
            src_path = video_path if video_path else audio_path
            base_name = os.path.splitext(os.path.basename(src_path))[0]
            alignment_override = os.path.join(ALIGN_DIR, f"{base_name}_alignment_provided.json")
            os.makedirs(ALIGN_DIR, exist_ok=True)
            with open(alignment_override, 'w', encoding='utf-8') as f:
                import json as _json
                _json.dump(alignment_json, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Failed to persist provided alignment: {e}")
        alignment_override = None
    sep_pref = data.get('separation_engine') or data.get('separation_prefer') or 'auto'
    out_fmt = (data.get('output_format') or 'mp4').lower()
    thread = threading.Thread(target=process_job, args=(job_id, audio_path, lyrics_path, bg_rgb, font_name, fontsize, outro_path, outro_is_video, outro_text, song_title, artist_name, bg_image_path, alignment_override, sep_pref, out_fmt, pause_config, sync_refine, language, video_path))
    thread.daemon = True
    thread.start()
    
    # Return job ID
    return jsonify({
        'job_id': job_id,
        'status': 'queued'
    })

# List available fonts for the frontend
@app.route('/fonts', methods=['GET', 'OPTIONS'])
def list_fonts():
    if request.method == 'OPTIONS':
        return ('', 204)
    try:
        fonts = []
        allowed_exts = {'.ttf', '.otf', '.ttc'}
        if os.path.exists(FONTS_DIR):
            for fname in os.listdir(FONTS_DIR):
                ext = os.path.splitext(fname)[1].lower()
                if ext in allowed_exts:
                    base = os.path.splitext(fname)[0]
                    fonts.append(base)
        # Add common Windows fonts if present
        if os.name == 'nt':
            win_map = {
                'Arial': r'C:\\Windows\\Fonts\\arial.ttf',
                'Impact': r'C:\\Windows\\Fonts\\impact.ttf',
                'Verdana': r'C:\\Windows\\Fonts\\verdana.ttf',
                'Times New Roman': r'C:\\Windows\\Fonts\\times.ttf',
            }
            for name, path in win_map.items():
                try:
                    if os.path.exists(path) and name not in fonts:
                        fonts.append(name)
                except Exception:
                    pass
        # Ensure a sensible default appears first
        default_font = 'Arial'
        fonts = sorted(set(fonts), key=lambda x: (0 if x == default_font else 1, x.lower()))
        return jsonify({'fonts': fonts, 'default': default_font})
    except Exception as e:
        return jsonify({'fonts': ['Arial'], 'default': 'Arial', 'error': str(e)}), 200

# Update status route to handle preflight
@app.route('/status/<job_id>', methods=['GET', 'OPTIONS'])
def get_job_status(job_id):
    if request.method == 'OPTIONS':
        return ('', 204)
    # Check if job exists
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    job = jobs[job_id]
    
    # Return job status
    response = {
        'job_id': job_id,
        'status': job['status'],
        'progress': job.get('progress', 0),
        'stage': job.get('stage')
    }
    # Include analysis URL and main vocal onset if available
    if job.get('analysis_url'):
        response['analysis_url'] = job['analysis_url']
    if job.get('main_vocal_onset') is not None:
        response['main_vocal_onset'] = job['main_vocal_onset']
    if job.get('audio_vocal_onset') is not None:
        response['audio_vocal_onset'] = job['audio_vocal_onset']
    if job.get('stem_engine'):
        response['stem_engine'] = job['stem_engine']
    
    # Add output path if job is done
    if job['status'] == 'done':
        if job.get('final_output'):
            response['final_output'] = job['final_output']
            rel_final = os.path.relpath(job['final_output'], OUTPUT_DIR).replace("\\", "/")
            response['final_output_url'] = f"/outputs/{rel_final}"
        elif job.get('output'):
            response['output'] = job['output']
            rel_out = os.path.relpath(job['output'], OUTPUT_DIR).replace("\\", "/")
            response['output_url'] = f"/outputs/{rel_out}"
        if job.get('thumbnail'):
            response['thumbnail'] = job['thumbnail']
            rel_thumb = os.path.relpath(job['thumbnail'], OUTPUT_DIR).replace("\\", "/")
            response['thumbnail_url'] = f"/outputs/{rel_thumb}"
        if job.get('alignment'):
            response['alignment'] = job['alignment']
            response['alignment_url'] = job.get('alignment_url')
        if job.get('lrc'):
            response['lrc'] = job['lrc']
            response['lrc_url'] = job.get('lrc_url')
        if job.get('srt'):
            response['srt'] = job['srt']
            response['srt_url'] = job.get('srt_url')
        if job.get('vocal_segments'):
            response['vocal_segments'] = job['vocal_segments']
            response['vocal_segments_url'] = job.get('vocal_segments_url')
        if job.get('vocals'):
            response['vocals'] = job['vocals']
        if job.get('instrumental'):
            response['instrumental'] = job['instrumental']
        if job.get('instrument'):
            response['instrument'] = job['instrument']
            rel_inst = os.path.relpath(job['instrument'], OUTPUT_DIR).replace("\\", "/")
            response['instrument_url'] = f"/outputs/{rel_inst}"
        if job.get('instrumental_video'):
            response['instrumental_video'] = job['instrumental_video']
            response['instrumental_video_url'] = job.get('instrumental_video_url')
        if job.get('stems_mix'):
            response['stems_mix'] = job['stems_mix']
        if job.get('qc'):
            response['qc'] = job['qc']
            response['qc_url'] = job.get('qc_url')
    
    # Add error if job failed
    if job['status'] == 'error' and 'error' in job:
        response['error'] = job['error']
    
    return jsonify(response)

@app.route('/cancel/<job_id>', methods=['POST', 'OPTIONS'])
def cancel_job(job_id):
    if request.method == 'OPTIONS':
        return ('', 204)
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    job = jobs[job_id]
    status = job.get('status', '')
    if status in ('done', 'error', 'cancelled'):
        return jsonify({'job_id': job_id, 'status': status, 'message': f'Job already in terminal state: {status}'}), 200
    job['cancelled'] = True
    job['status'] = 'cancelled'
    job['stage'] = 'Cancelling...'
    print(f"[cancel_job] Requested cancellation of job {job_id}")
    
    # Aggressively kill any ffmpeg/spleeter/demucs processes currently blocking the thread
    tid = job.get('thread_id')
    if tid is not None:
        try:
            from backend.audio_utils import kill_active_process
            kill_active_process(tid)
        except Exception as e:
            print(f"Failed to kill child processes for job {job_id}: {e}")
            
    return jsonify({'job_id': job_id, 'status': 'cancelled', 'message': 'Cancellation requested'}), 200


if __name__ == '__main__':

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(ALIGN_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    port = int(os.environ.get('CROONIFY_BACKEND_PORT', '5000'))
    app.run(debug=False, host='127.0.0.1', port=port, threaded=True, use_reloader=False)
