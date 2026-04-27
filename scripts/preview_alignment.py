import json, sys

path = sys.argv[1] if len(sys.argv) > 1 else r'alignments\20260411_174849_alignment.json'

with open(path, encoding='utf-8') as f:
    data = json.load(f)

frags = data['fragments']
non_blank = [fr for fr in frags if fr.get('lines') and fr['lines'][0].strip()]

properly_aligned = [fr for fr in non_blank if (float(fr['end']) - float(fr['begin'])) >= 0.05]
collapsed = [fr for fr in non_blank if (float(fr['end']) - float(fr['begin'])) < 0.05]

duration = float(frags[-1]['end'])

print(f"Song duration : {duration:.2f}s  ({duration/60:.1f} min)")
print(f"Total lines   : {len(frags)} (inc. {len(frags)-len(non_blank)} blank)")
print(f"Non-blank     : {len(non_blank)}")
print(f"Good alignment: {len(properly_aligned)}")
print(f"Collapsed     : {len(collapsed)}")
print()

# Find collapse start
print("=" * 70)
print("FULL ALIGNMENT (all non-blank lines):")
print("=" * 70)
for i, fr in enumerate(non_blank):
    begin = float(fr['begin'])
    end = float(fr['end'])
    dur = end - begin
    line = fr['lines'][0][:60]
    flag = " <<< COLLAPSED" if dur < 0.05 else ""
    print(f"  {i+1:2d}. [{begin:6.2f}s -> {end:6.2f}s | {dur:.2f}s]  {line}{flag}")
