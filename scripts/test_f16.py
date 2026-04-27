import json, sys

path = r'alignments/20260417_141917_audio_whisperx.json'
try:
    with open(path, encoding='utf-8') as f:
        wx = json.load(f)

    # Find any words in whispered matched by the text from f16.
    print("Whisper words containing 'when' or 'feel' or 'like':")
    for seg in wx.get('segments',[]):
       for w in seg.get('words',[]):
           t = w.get('word','').lower()
           if 'when' in t or 'feel' in t or 'like' in t:
               print(f"[{w.get('start', 0):.3f}->{w.get('end', 0):.3f}] {t}")
except Exception as e:
    print(e)
