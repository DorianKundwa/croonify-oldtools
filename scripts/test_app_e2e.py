"""
End-to-end smoke test for the Croonify backend with WhisperX.
Submits a real job and polls until completion.
"""
import requests
import time
import sys
import json

BASE = "http://localhost:5000"
AUDIO  = r"uploads\20260411_174849_audio.mp3"
LYRICS = r"uploads\20260411_174849_lyrics.txt"

def main():
    # 1. Health check
    try:
        r = requests.get(f"{BASE}/", timeout=5)
        print(f"[1] Health: {r.status_code} OK")
    except Exception as e:
        print(f"[1] Server not reachable: {e}")
        sys.exit(1)

    # 2. Submit job
    print("\n[2] Submitting generate job...")
    with open(AUDIO, "rb") as af, open(LYRICS, "rb") as lf:
        r = requests.post(
            f"{BASE}/generate",
            files={
                "audio":  ("audio.mp3", af, "audio/mpeg"),
                "lyrics": ("lyrics.txt", lf, "text/plain"),
            },
            data={"language": "eng", "bg_color": "#0a0a0a"},
            timeout=30,
        )

    if r.status_code != 200:
        print(f"[2] Submit failed: {r.status_code} {r.text[:300]}")
        sys.exit(1)

    resp = r.json()
    job_id = resp.get("job_id")
    print(f"[2] Job submitted: {job_id}  status={resp.get('status')}")

    if not job_id:
        print("[2] No job_id returned - aborting")
        sys.exit(1)

    # 3. Poll for completion
    print("\n[3] Polling job status...")
    start = time.time()
    timeout = 600  # 10 min max for transcription + video
    last_stage = ""

    while True:
        elapsed = time.time() - start
        if elapsed > timeout:
            print(f"[3] Timed out after {timeout}s")
            sys.exit(1)

        time.sleep(4)
        try:
            r = requests.get(f"{BASE}/status/{job_id}", timeout=10)
            job = r.json()
        except Exception as e:
            print(f"[3] Poll error: {e}")
            continue

        status   = job.get("status", "?")
        stage    = job.get("stage", "?")
        progress = job.get("progress", 0)

        if stage != last_stage:
            print(f"  [{elapsed:5.0f}s] stage={stage!r:40s}  progress={progress}%  status={status}")
            last_stage = stage

        if status == "completed":
            print(f"\n[3] ✅ Job COMPLETED in {elapsed:.1f}s")
            print(f"     Video URL : {job.get('video_url', 'N/A')}")
            print(f"     Align URL : {job.get('alignment_url', 'N/A')}")
            break

        if status == "error":
            print(f"\n[3] ❌ Job FAILED: {job.get('error', 'unknown')}")
            print(json.dumps(job, indent=2)[:1000])
            sys.exit(1)

if __name__ == "__main__":
    main()
