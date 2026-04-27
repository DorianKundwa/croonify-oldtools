import sys
sys.path.append('backend')
from alignment_whisperx import _line_bounds_from_anchors, _fill_word_gaps, _enforce_global_monotonicity, MIN_LINE_DUR
prev_end = 179.5
audio_duration = 180.0
fragments = []
for i in range(10):
    ms = [None]; me = [None]; mf = [False]; toks = ['word']
    f_begin, f_end = _line_bounds_from_anchors(ms, me, prev_end, None, audio_duration, len(toks))
    words = [{'text': 'word', 'start': 0.0, 'end': 0.0}]
    _fill_word_gaps(words, f_begin, f_end, mf)
    f_begin = max(prev_end + 0.01, min(w['start'] for w in words))
    f_end = max(f_begin + MIN_LINE_DUR, max(w['end'] for w in words))
    fragments.append({'begin': f'{f_begin:.3f}', 'end': f'{f_end:.3f}', 'words': [{'start': w['start'], 'end': w['end']} for w in words]})
    prev_end = f_end
_enforce_global_monotonicity(fragments)
for f in fragments: print(f"{f['begin']} -> {f['end']}")
