"""
Analyze alignment JSON to identify problems: long stretches, collapsed lines,
monotonicity violations, and word-level timestamp gaps.
"""
import json
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "alignments/20260412_115807_new.json"
with open(path, "r", encoding="utf-8") as f:
    d = json.load(f)

frags = d["fragments"]
print(f"Total fragments: {len(frags)}")
print()

LONG_THRESH = 5.0
COLLAPSED_THRESH = 0.15

issues = []
prev_end = 0.0

for i, frag in enumerate(frags):
    start = float(frag["begin"])
    end   = float(frag["end"])
    dur   = end - start
    txt   = frag["lines"][0] if isinstance(frag["lines"], list) else frag["lines"]
    words = frag.get("words", [])

    flags = []
    if dur > LONG_THRESH:
        flags.append(f"LONG({dur:.1f}s)")
    if dur < COLLAPSED_THRESH and len(words) > 1:
        flags.append("COLLAPSED")
    if start < prev_end - 0.05:
        flags.append(f"OVERLAP(prev_end={prev_end:.2f})")

    # Check word-level monotonicity
    last_w_end = 0.0
    for w in words:
        ws = w.get("start", 0)
        we = w.get("end", 0)
        if ws < last_w_end - 0.05:
            flags.append(f"WORD_BACK({w.get('text','?')}@{ws:.2f}<{last_w_end:.2f})")
        last_w_end = we

    flag_str = "  <<< " + ", ".join(flags) if flags else ""
    print(f"{i+1:3}. [{start:7.2f} -> {end:7.2f} | {dur:5.2f}s | w:{len(words)}]{flag_str}")
    if flags:
        print(f"       {txt[:80]}")
        if "LONG" in " ".join(flags):
            print(f"       Words: {[(w.get('text','?'), round(w.get('start',0),2), round(w.get('end',0),2)) for w in words]}")

    if flags:
        issues.append((i + 1, flags, txt))

    prev_end = end

print()
print(f"{'='*60}")
print(f"Summary: {len(issues)} problematic fragments out of {len(frags)}")
for line_no, flags, txt in issues:
    print(f"  Line {line_no}: {', '.join(flags)} -- {txt[:60]}")
