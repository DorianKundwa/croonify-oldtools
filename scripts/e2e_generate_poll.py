import os
import time
import json
import requests


def main():
    base = "http://127.0.0.1:5000"
    audio_path = os.path.abspath(os.path.join("uploads", "test.mp3"))
    lyrics_path = os.path.abspath(os.path.join("uploads", "test_lyrics.txt"))

    payload = {
        "audio_path": audio_path,
        "lyrics_path": lyrics_path,
        "bg_color": "#222222",
    }

    print("POST /generate with:", json.dumps(payload, indent=2))
    r = requests.post(f"{base}/generate", json=payload, timeout=60)
    print("Generate status:", r.status_code)
    print("Generate response:", r.text[:500])
    r.raise_for_status()
    job_id = r.json()["job_id"]
    print("Job ID:", job_id)

    deadline = time.time() + 600  # 10 minutes
    last_stage = None
    data = {}
    while time.time() < deadline:
        s = requests.get(f"{base}/status/{job_id}", timeout=60)
        if s.status_code != 200:
            print("Status error:", s.status_code, s.text[:200])
            time.sleep(3)
            continue
        data = s.json()
        prog = data.get("progress", 0)
        stage = data.get("stage")
        status = data.get("status")
        if stage != last_stage:
            print("Stage:", stage)
            last_stage = stage
        print(f"Progress: {prog}% Status: {status}")
        if status == "done":
            out = data.get("output_url")
            full = f"{base}{out}" if out else None
            print("FINAL_OUTPUT_URL:", full)
            break
        if status == "error":
            print("ERROR:", data.get("error"))
            break
        time.sleep(5)

    print("Final status payload:", json.dumps(data, indent=2))


if __name__ == "__main__":
    main()