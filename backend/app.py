from flask import Flask, request, jsonify
import os
import datetime
import threading
import uuid
import time
import subprocess
import werkzeug.utils

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
    )
    from backend.audio_utils import (
        convert_to_wav,
        normalize_audio,
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
    )
    from backend.alignment_aeneas import align
    from backend.video_builder import build_lyric_video, generate_thumbnail_image, _find_font_path
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
    )
    from audio_utils import (
        convert_to_wav,
        normalize_audio,
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
    )
    from alignment_aeneas import align
    from video_builder import build_lyric_video, generate_thumbnail_image, _find_font_path

# Job management
jobs = {}  # Dictionary to store job status: {job_id: {"status": "queued|running|done", "output": None}}

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
    if 'audio' not in request.files:
        return jsonify({'error': 'Missing audio file'}), 400
    
    audio_file = request.files['audio']
    lyrics_file = request.files.get('lyrics')
    outro_file = request.files.get('outro')
    bg_file = request.files.get('background')
    
    # Check audio validity
    if audio_file.filename == '':
        return jsonify({'error': 'No audio file selected'}), 400
    
    # Check audio file extension
    audio_ext = os.path.splitext(audio_file.filename)[1].lower()
    allowed_exts = ['.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg', '.wma', '.aiff', '.aif', '.mp4', '.webm', '.opus']
    if audio_ext not in allowed_exts:
        return jsonify({'error': 'Audio file must be one of: MP3, WAV, M4A, AAC, FLAC, OGG, WMA, AIFF, MP4, WEBM, OPUS'}), 400
    
    # If lyrics file provided, check extension
    if lyrics_file and lyrics_file.filename:
        lyrics_ext = os.path.splitext(lyrics_file.filename)[1].lower()
        if lyrics_ext not in ('.txt', '.lrc'):
            return jsonify({'error': 'Lyrics file must be TXT or LRC format'}), 400

    # If outro audio provided, check extension
    if outro_file and outro_file.filename:
        outro_ext = os.path.splitext(outro_file.filename)[1].lower()
        allowed_exts = ['.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg', '.wma', '.aiff', '.aif', '.mp4', '.webm', '.opus']
        if outro_ext not in allowed_exts:
            return jsonify({'error': 'Outro audio must be one of: MP3, WAV, M4A, AAC, FLAC, OGG, WMA, AIFF, MP4, WEBM, OPUS'}), 400
    
    # Generate timestamp for unique filenames
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save audio file
    audio_filename = f"{timestamp}_audio{audio_ext}"
    audio_path = os.path.join(UPLOAD_DIR, audio_filename)
    audio_file.save(audio_path)
    
    # Save lyrics file if provided, else rely on typed lyrics from form
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
        'audio_path': audio_path,
        'lyrics_path': lyrics_path,
        'outro_path': outro_path,
        'background_path': background_path
    })

def _append_outro_async(job_id, base_video_path, outro_path, bg_color=None, bg_image_path=None, font_name=None, font_size=None):
    """Post-processing: create an outro segment (image or solid color + outro audio)
    and append to the already-rendered base video using fast concat when possible.
    Updates jobs[job_id] with final_output and final_output_url upon completion.
    """
    try:
        if not (outro_path and os.path.exists(outro_path) and base_video_path and os.path.exists(base_video_path)):
            return

        # Convert outro audio to WAV for consistent handling
        outro_base = os.path.splitext(os.path.basename(outro_path))[0]
        outro_wav = os.path.join(UPLOAD_DIR, f"{outro_base}.wav")
        try:
            convert_to_wav(outro_path, outro_wav)
            # Normalize outro WAV to avoid clipping or level jumps
            normalize_audio(outro_wav, outro_wav)
        except Exception as e:
            print(f"Outro conversion failed: {e}")
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
        preset = FFMPEG_PRESET or 'ultrafast'
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
        dt = f"drawtext={font_expr}:text='Thanks for watching':x=(w-text_w)/2:y=(h-text_h)/2:fontcolor=white:fontsize={out_fs}:box=1:boxcolor=black@0.35"
        if use_image:
            ffmpeg_cmd = [
                FFMPEG_PATH, '-y',
                '-loop', '1', '-i', bg_image_path,
                '-i', outro_wav,
                '-vf', f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,{dt}",
                '-c:v', encoder, '-preset', str(preset),
                *( ['-tune', str(tune)] if tune else [] ),
                *( ['-crf', str(crf)] if crf else ['-b:v', '3000k'] ),
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
                *( ['-crf', str(crf)] if crf else ['-b:v', '3000k'] ),
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
                    *( ['-crf', str(crf)] if crf else ['-b:v', '3000k'] ),
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
                return

        # Update job with final output
        try:
            jobs[job_id]["final_output"] = final_path
            # Use relpath to preserve session subfolder in URL
            rel_final = os.path.relpath(final_path, OUTPUT_DIR).replace("\\", "/")
            jobs[job_id]["final_output_url"] = f"/outputs/{rel_final}"
            jobs[job_id]["stage"] = "Completed (outro appended)"
        except Exception:
            pass

        # After final is obtained, delete base lyrics video, outro segment and concat list
        try:
            for p in [base_video_path, outro_segment, filelist_path]:
                try:
                    if p and os.path.exists(p):
                        os.remove(p)
                except Exception as de:
                    print(f"Cleanup warning: failed to delete {p}: {de}")
            # Clear base output in job to avoid dangling links
            try:
                jobs[job_id]["output"] = None
                jobs[job_id]["output_url"] = None
            except Exception:
                pass
        except Exception:
            pass
    finally:
        # best-effort cleanup
        try:
            if 'outro_segment' in locals() and os.path.exists(outro_segment):
                pass  # keep segment for debugging; remove if desired
        except Exception:
            pass


def _render_instrument_video_async(job_id, instrumental_path, bg_color=None, bg_image_path=None, outro_path=None, session_dir=None, base_name=None, font_name=None, font_size=None):
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
        preset = FFMPEG_PRESET or 'ultrafast'
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
                '-vf', f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1",
                '-c:v', encoder, '-preset', str(preset),
                *( ['-tune', str(tune)] if tune else [] ),
                *( ['-crf', str(crf)] if crf else ['-b:v', '3000k'] ),
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
                *( ['-crf', str(crf)] if crf else ['-b:v', '3000k'] ),
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
        if outro_path and os.path.exists(outro_path):
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
            dt2 = f"drawtext={font_expr2}:text='Thanks for watching':x=(w-text_w)/2:y=(h-text_h)/2:fontcolor=white:fontsize={out_fs2}:box=1:boxcolor=black@0.35"
            if use_image:
                outro_cmd = [
                    FFMPEG_PATH, '-y',
                    '-loop', '1', '-i', bg_image_path,
                    '-i', outro_wav,
                    '-vf', f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,{dt2}",
                    '-c:v', encoder, '-preset', str(preset),
                    *( ['-tune', str(tune)] if tune else [] ),
                    *( ['-crf', str(crf)] if crf else ['-b:v', '3000k'] ),
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
                    *( ['-crf', str(crf)] if crf else ['-b:v', '3000k'] ),
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
                try:
                    reenc_cmd = [
                        FFMPEG_PATH, '-y',
                        '-i', instrument_segment,
                        '-i', outro_segment,
                        '-filter_complex', '[0:v:0][0:a:0][1:v:0][1:a:0]concat=n=2:v=1:a=1[v][a]',
                        '-map', '[v]', '-map', '[a]',
                        '-c:v', encoder, '-preset', str(preset),
                        *( ['-tune', str(tune)] if tune else [] ),
                        *( ['-crf', str(crf)] if crf else ['-b:v', '3000k'] ),
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
            if 'instrument_segment' in locals() and instrument_segment and os.path.exists(instrument_segment):
                if final_path != instrument_segment:
                    os.remove(instrument_segment)
            if 'outro_segment' in locals() and outro_segment and os.path.exists(outro_segment):
                os.remove(outro_segment)
        except Exception:
            pass
    except Exception:
        pass


def process_job(job_id, audio_path, lyrics_path, bg_color=None, font_name=None, fontsize=None, outro_path=None, song_title=None, artist_name=None, bg_image_path=None, alignment_override=None, separation_prefer='auto', output_format='mp4', pause_config=None, sync_refine=False, language=None):
    """Background thread function to process a job"""
    try:
        # Update job status
        jobs[job_id]["status"] = "running"
        jobs[job_id]["progress"] = 0
        jobs[job_id]["stage"] = "Starting job"
        
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

        # Step 3: Align full-mix audio with lyrics using Aeneas
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
                    from backend.alignment_aeneas import lrc_to_alignment
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

        # No cross-correlation shifting; use raw alignment times

        try:
            if bool(sync_refine):
                rp = refine_word_alignment(vocals_path or wav_path, alignment_path)
                if rp and os.path.exists(rp):
                    alignment_path = rp
                    jobs[job_id]["alignment"] = alignment_path
                    rel_align = os.path.relpath(alignment_path, ALIGN_DIR).replace("\\", "/")
                    jobs[job_id]["alignment_url"] = f"/alignments/{rel_align}"
                sp = refine_syllable_alignment(alignment_path, os.path.join(ALIGN_DIR, f"{base_name}_alignment_syllables.json"), syllable_offset_ms=0.0)
                if sp and os.path.exists(sp):
                    alignment_path = sp
                    jobs[job_id]["alignment"] = alignment_path
                    rel_align = os.path.relpath(alignment_path, ALIGN_DIR).replace("\\", "/")
                    jobs[job_id]["alignment_url"] = f"/alignments/{rel_align}"
        except Exception:
            pass

        # Create per-session output directory named "song_artist" (sanitized)
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

        main_vocal_onset = None
        try:
            main_vocal_onset = detect_main_vocal_onset_from_alignment(alignment_path)
        except Exception:
            main_vocal_onset = None
        audio_vocal_onset = None
        try:
            onset_src = vocals_path if (vocals_path and os.path.exists(vocals_path)) else wav_path
            audio_vocal_onset = detect_vocal_onset(onset_src)
        except Exception:
            audio_vocal_onset = None
        try:
            jobs[job_id]["main_vocal_onset"] = main_vocal_onset
            jobs[job_id]["audio_vocal_onset"] = audio_vocal_onset
        except Exception:
            pass

        # No onset-based shifting; display times exactly as in JSON

        # Step 3.5: Prepare final audio (use normalized full mix)
        jobs[job_id]["stage"] = "Preparing final mix"
        jobs[job_id]["progress"] = 66
        audio_final_path = wav_path

        breaks = []
        try:
            cfg = pause_config or {}
            thr = cfg.get('threshold_db') or '-25dB'
            ms = cfg.get('min_silence_sec') or 0.4
            fw = cfg.get('flux_window_sec') or 0.25
            mp = cfg.get('min_pause_sec') or 0.2
            breaks = detect_breaks_and_pauses(vocals_path or wav_path, noise_threshold_db=str(thr), min_silence_dur=float(ms), flux_window_sec=float(fw), min_pause_sec=float(mp))
            try:
                bp = os.path.join(ALIGN_DIR, f"{base_name}_breaks.json")
                import json as _json
                with open(bp, 'w', encoding='utf-8') as f:
                    _json.dump({'breaks': breaks}, f, ensure_ascii=False, indent=2)
                jobs[job_id]["breaks"] = bp
                rel_bp = os.path.relpath(bp, ALIGN_DIR).replace("\\", "/")
                jobs[job_id]["breaks_url"] = f"/alignments/{rel_bp}"
            except Exception:
                pass
        except Exception:
            breaks = []
        # Step 4: Build video (use refined alignment times for lyric display)
        jobs[job_id]["stage"] = "Rendering lyric video"
        jobs[job_id]["progress"] = 70
        ext = str(output_format or 'mp4').lower()
        if ext not in ('mp4', 'mov'):
            ext = 'mp4'
        output_path = os.path.join(session_dir, f"{base_name}_lyrics.{ext}")
        try:
            print(f"Starting video render to '{output_path}' with alignment '{alignment_path}'")
        except Exception:
            pass
        result = build_lyric_video(
            audio_final_path,
            alignment_path,
            output_path,
            bg_image_path,
            bg_color,
            use_highlight=False,
            progress_callback=lambda p: update_job_progress(job_id, 70 + int(max(0.0, min(1.0, p)) * 29)),
            font_name=font_name,
            fontsize=fontsize or 70,
            outro_audio_path=None,
            vocal_onset=None,
            trim_intro=False,
            trim_end_silence=False,
            pause_markers=breaks,
            pause_opacity=0.22
        )
        if not result or not os.path.exists(output_path):
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = (
                "Video rendering failed. Verify FFmpeg is available and inputs are correct."
            )
            return
        
        # Update job status
        jobs[job_id]["status"] = "done"
        jobs[job_id]["stage"] = "Completed (base video)"
        jobs[job_id]["progress"] = 100
        jobs[job_id]["output"] = output_path
        rel_output = os.path.relpath(output_path, OUTPUT_DIR).replace("\\", "/")
        jobs[job_id]["output_url"] = f"/outputs/{rel_output}"

        try:
            def _compute_analysis_async():
                try:
                    from backend.audio_utils import classify_vocal_segments_enhanced
                    a = classify_vocal_segments_enhanced(wav_path, alignment_path, vocals=vocals_path, instrumental=instrumental_path)
                    if a and isinstance(a, dict):
                        ap = os.path.join(session_dir, f"{base_name}_vocal_analysis.json")
                        with open(ap, 'w', encoding='utf-8') as f:
                            import json as _json
                            _json.dump(a, f, ensure_ascii=False, indent=2)
                        jobs[job_id]["analysis"] = ap
                        rel_analysis = os.path.relpath(ap, OUTPUT_DIR).replace("\\", "/")
                        jobs[job_id]["analysis_url"] = f"/outputs/{rel_analysis}"
                        try:
                            jobs[job_id]["main_vocal_onset"] = a.get("main_vocal_onset")
                        except Exception:
                            pass
                except Exception:
                    pass
            t = threading.Thread(target=_compute_analysis_async)
            t.daemon = True
            t.start()
        except Exception:
            pass

        try:
            if vocals_path and os.path.exists(vocals_path):
                segs = detect_vocal_segments_from_stem(vocals_path)
                seg_path = os.path.join(ALIGN_DIR, f"{base_name}_vocal_segments.json")
                import json as _json
                with open(seg_path, 'w', encoding='utf-8') as f:
                    _json.dump({'segments': segs}, f, ensure_ascii=False, indent=2)
                jobs[job_id]["vocal_segments"] = seg_path
                rel_segs = os.path.relpath(seg_path, ALIGN_DIR).replace("\\", "/")
                jobs[job_id]["vocal_segments_url"] = f"/alignments/{rel_segs}"
        except Exception:
            pass

        try:
            lrc_out = os.path.join(ALIGN_DIR, f"{base_name}.lrc")
            srt_out = os.path.join(ALIGN_DIR, f"{base_name}.srt")
            lrcp, srtp = export_alignment_formats(alignment_path, lrc_out, srt_out)
            if lrcp:
                jobs[job_id]["lrc"] = lrcp
                rel_lrc = os.path.relpath(lrcp, ALIGN_DIR).replace("\\", "/")
                jobs[job_id]["lrc_url"] = f"/alignments/{rel_lrc}"
            if srtp:
                jobs[job_id]["srt"] = srtp
                rel_srt = os.path.relpath(srtp, ALIGN_DIR).replace("\\", "/")
                jobs[job_id]["srt_url"] = f"/alignments/{rel_srt}"
        except Exception:
            pass

        try:
            if vocals_path and instrumental_path:
                qc = compute_separation_quality(vocals_path, instrumental_path, wav_path)
                qc_path = os.path.join(ALIGN_DIR, f"{base_name}_qc.json")
                import json as _json
                with open(qc_path, 'w', encoding='utf-8') as f:
                    _json.dump(qc, f, ensure_ascii=False, indent=2)
                jobs[job_id]["qc"] = qc_path
                rel_qc = os.path.relpath(qc_path, ALIGN_DIR).replace("\\", "/")
                jobs[job_id]["qc_url"] = f"/alignments/{rel_qc}"
        except Exception:
            pass

        # Generate thumbnail image (uses background image or color and selected font)
        try:
            thumb_path = os.path.join(session_dir, f"{base_name}_thumbnail.png")
            base_fs = int(fontsize or 70)
            # Larger multipliers per request: title ≈ 6.5×, artist ≈ 2.5×
            title_fs = int(base_fs * 6.5)
            artist_fs = max(32, int(base_fs * 2.5))
            generated = generate_thumbnail_image(
                title=song_title or os.path.splitext(os.path.basename(lyrics_path or ''))[0],
                artist=artist_name or '',
                out_path=thumb_path,
                bg_color=bg_color,
                image_path=bg_image_path,
                font_name=font_name,
                title_fontsize=title_fs,
                artist_fontsize=artist_fs,
            )
            if generated:
                jobs[job_id]["thumbnail"] = thumb_path
                rel_thumb = os.path.relpath(thumb_path, OUTPUT_DIR).replace("\\", "/")
                jobs[job_id]["thumbnail_url"] = f"/outputs/{rel_thumb}"
        except Exception as e:
            print(f"Thumbnail generation error: {e}")

        # Kick off post-processing to append outro without blocking main completion
        try:
            jobs[job_id]["postprocess"] = "appending_outro" if outro_path else None
            if outro_path:
                t = threading.Thread(target=_append_outro_async, args=(job_id, output_path, outro_path, bg_color, bg_image_path, font_name, fontsize or 70))
                t.daemon = True
                t.start()
        except Exception as e:
            print(f"Failed to start outro append thread: {e}")
        try:
            if instrumental_path and os.path.exists(instrumental_path):
                t2 = threading.Thread(target=_render_instrument_video_async, args=(job_id, instrumental_path, bg_color, bg_image_path, outro_path, session_dir, base_name, font_name, fontsize or 70))
                t2.daemon = True
                t2.start()
        except Exception:
            pass
        
    except Exception as e:
        # Update job status with error
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)

# Update generate route to handle preflight
@app.route('/generate', methods=['POST', 'OPTIONS'])
def generate_video():
    if request.method == 'OPTIONS':
        return ('', 204)
    # Get request data
    data = request.json
    
    # Validate request
    if not data or 'audio_path' not in data or 'lyrics_path' not in data:
        return jsonify({'error': 'Missing audio_path or lyrics_path'}), 400
    
    audio_path = data['audio_path']
    lyrics_path = data['lyrics_path']
    bg_color_str = data.get('bg_color')
    bg_rgb = parse_bg_color(bg_color_str) if bg_color_str else None
    bg_image_path = data.get('bg_image')
    font_name = data.get('font')
    fontsize = data.get('fontsize')
    alignment_json = data.get('alignment_json')
    language = data.get('language')
    pause_config = data.get('pause')
    sync_refine = data.get('sync_refine', False)
    
    outro_path = data.get('outro_path')
    song_title = data.get('song_title')
    artist_name = data.get('artist_name')
    
    # Check if files exist
    if not os.path.exists(audio_path):
        return jsonify({'error': f'Audio file not found: {audio_path}'}), 404
    
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
            base_name = os.path.splitext(os.path.basename(audio_path))[0]
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
    thread = threading.Thread(target=process_job, args=(job_id, audio_path, lyrics_path, bg_rgb, font_name, fontsize, outro_path, song_title, artist_name, bg_image_path, alignment_override, sep_pref, out_fmt, pause_config, sync_refine, language))
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
        if job.get('stems_mix'):
            response['stems_mix'] = job['stems_mix']
        if job.get('qc'):
            response['qc'] = job['qc']
            response['qc_url'] = job.get('qc_url')
    
    # Add error if job failed
    if job['status'] == 'error' and 'error' in job:
        response['error'] = job['error']
    
    return jsonify(response)

if __name__ == '__main__':
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(ALIGN_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    port = int(os.environ.get('CROONIFY_BACKEND_PORT', '5000'))
    app.run(debug=False, host='127.0.0.1', port=port, threaded=True, use_reloader=False)
