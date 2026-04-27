import json, sys

path = sys.argv[1] if len(sys.argv) > 1 else r'alignments\20260417_141917_audio_alignment.json'

with open(path, encoding='utf-8') as f:
    data = json.load(f)

frags = data['fragments']
print("Fragments 44-56s (fragments around the broken zone):")
for i, fr in enumerate(frags):
    begin = float(fr['begin'])
    end = float(fr['end'])
    if 44 <= begin <= 56:
        dur = end - begin
        matched = sum(1 for w in fr.get('words',[]) if w.get('matched_by','') not in ('interpolated','heuristic'))
        total = len(fr.get('words',[]))
        line = fr['lines'][0][:60] if fr.get('lines') else ''
        print(f"  [{i+1:3d}] [{begin:.3f}s->{end:.3f}s | dur={dur:.3f}s | {matched}/{total} ASR-matched]  {line}")

# Show the large time gap
print()
print("Time gaps between consecutive fragments:")
for i in range(len(frags) - 1):
    b1 = float(frags[i]['end'])
    b2 = float(frags[i+1]['begin'])
    gap = b2 - b1
    if gap > 0.5 and 40 <= float(frags[i]['begin']) <= 60:
        line = frags[i]['lines'][0][:40] if frags[i].get('lines') else ''
        nline = frags[i+1]['lines'][0][:40] if frags[i+1].get('lines') else ''
        print(f"  [{i+1}]->[{i+2}]: gap={gap:.3f}s  after: '{line}' | before: '{nline}'")

print()
# Show what ASR words exist in 45-50s range
# We'll need to find the whisperx raw file
import os
whisperx_path = path.replace('_alignment.json', '_whisperx.json')
if os.path.exists(whisperx_path):
    with open(whisperx_path, encoding='utf-8') as f:
        wx = json.load(f)
    print("ASR words in 45-50s range from WhisperX raw output:")
    for seg in wx.get('segments', []):
        for w in seg.get('words', []):
            ws = w.get('start', 0)
            we = w.get('end', 0)
            if 44 <= ws <= 52:
                print(f"  [{ws:.3f}s->{we:.3f}s] '{w.get('word','')}'")
else:
    print(f"No whisperx file at {whisperx_path}")
