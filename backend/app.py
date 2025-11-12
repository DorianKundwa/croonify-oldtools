from flask import Flask, request, jsonify, send_from_directory
import os
import datetime
import threading
import uuid
import time
import logging

# Import config directly since we're in the same directory
from config import UPLOAD_DIR, ALIGN_DIR, OUTPUT_DIR, FFMPEG_PATH, LOG_DIR
from audio_utils import convert_to_wav, normalize_audio
from alignment_aeneas import align
from video_builder import build_lyric_video
from flask_cors import CORS

# Job management
jobs = {}  # Dictionary to store job status: {job_id: {"status": "queued|running|done", "output": None}}

app = Flask(__name__)
CORS(app)

@app.route('/', methods=['GET'])
def index():
    return "Croonify API Running"

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'audio' not in request.files:
        return jsonify({'error': 'Missing audio file'}), 400
    
    audio_file = request.files['audio']
    lyrics_file = request.files.get('lyrics')
    lyrics_text = request.form.get('lyrics_text')
    
    # Check if files are valid
    if audio_file.filename == '':
        return jsonify({'error': 'No selected audio file'}), 400
    if not lyrics_file and not lyrics_text:
        return jsonify({'error': 'Lyrics file or text is required'}), 400
    
    # Check audio file extension
    audio_ext = os.path.splitext(audio_file.filename)[1].lower()
    if audio_ext not in ['.mp3', '.wav']:
        return jsonify({'error': 'Audio file must be MP3 or WAV format'}), 400
    
    # Check lyrics file extension if a file was provided
    if lyrics_file:
        lyrics_ext = os.path.splitext(lyrics_file.filename)[1].lower()
        if lyrics_ext != '.txt':
            return jsonify({'error': 'Lyrics file must be TXT format'}), 400
    
    # Generate timestamp for unique filenames
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save audio file
    audio_filename = f"{timestamp}_audio{audio_ext}"
    audio_path = os.path.join(UPLOAD_DIR, audio_filename)
    audio_file.save(audio_path)
    
    # Save lyrics from file or text
    if lyrics_file:
        lyrics_filename = f"{timestamp}_lyrics.txt"
        lyrics_path = os.path.join(UPLOAD_DIR, lyrics_filename)
        lyrics_file.save(lyrics_path)
    else:
        lyrics_filename = f"{timestamp}_lyrics.txt"
        lyrics_path = os.path.join(UPLOAD_DIR, lyrics_filename)
        with open(lyrics_path, 'w', encoding='utf-8') as f:
            f.write(lyrics_text)
    
    return jsonify({
        'success': True,
        'audio_path': audio_path,
        'lyrics_path': lyrics_path
    })

def process_job(job_id, audio_path, lyrics_path):
    """Background thread function to process a job"""
    try:
        # Update job status
        jobs[job_id]["status"] = "running"
        
        # Step 1: Convert audio to WAV
        wav_path = os.path.join(UPLOAD_DIR, f"{os.path.splitext(os.path.basename(audio_path))[0]}.wav")
        convert_to_wav(audio_path, wav_path)
        
        # Step 2: Normalize audio
        wav_path = normalize_audio(wav_path)
        
        # Step 3: Align audio with lyrics
        alignment_path = os.path.join(ALIGN_DIR, f"{os.path.splitext(os.path.basename(audio_path))[0]}_alignment.json")
        align(wav_path, lyrics_path, alignment_path)
        
        # Step 4: Build video
        output_path = os.path.join(OUTPUT_DIR, f"{os.path.splitext(os.path.basename(audio_path))[0]}_lyrics.mp4")
        build_lyric_video(wav_path, alignment_path, output_path)
        
        # Update job status
        jobs[job_id]["status"] = "done"
        jobs[job_id]["output"] = output_path
        
    except Exception as e:
        # Update job status with error
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)
        logging.exception("Job %s failed", job_id)

@app.route('/generate', methods=['POST'])
def generate_video():
    # Get request data
    data = request.json
    
    # Validate request
    if not data or 'audio_path' not in data or 'lyrics_path' not in data:
        return jsonify({'error': 'Missing audio_path or lyrics_path'}), 400
    
    audio_path = data['audio_path']
    lyrics_path = data['lyrics_path']
    
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
    thread = threading.Thread(target=process_job, args=(job_id, audio_path, lyrics_path))
    thread.daemon = True
    thread.start()
    
    # Return job ID
    return jsonify({
        'job_id': job_id,
        'status': 'queued'
    })

@app.route('/status/<job_id>', methods=['GET'])
def get_job_status(job_id):
    # Check if job exists
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    job = jobs[job_id]
    
    # Return job status
    response = {
        'job_id': job_id,
        'status': job['status']
    }
    
    # Add output path if job is done
    if job['status'] == 'done' and job['output']:
        response['output'] = job['output']
        response['output_url'] = f"/outputs/{os.path.basename(job['output'])}"
    
    # Add error if job failed
    if job['status'] == 'error' and 'error' in job:
        response['error'] = job['error']
    
    return jsonify(response)

@app.route('/outputs/<path:filename>', methods=['GET'])
def serve_output(filename):
    return send_from_directory(OUTPUT_DIR, filename)

if __name__ == '__main__':
    # Ensure directories exist
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(ALIGN_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
        handlers=[
            logging.FileHandler(os.path.join(LOG_DIR, 'app.log')),
            logging.StreamHandler()
        ]
    )
    import shutil
    if shutil.which(FFMPEG_PATH) is None:
        raise RuntimeError(f"FFmpeg not found: {FFMPEG_PATH}")
    
    app.run(debug=True, host='0.0.0.0', port=5000)