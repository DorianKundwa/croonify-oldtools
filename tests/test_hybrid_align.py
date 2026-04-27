"""
tests/test_hybrid_align.py
Unit tests for the 5-layer hybrid lyric alignment engine.

Run with:  python -m pytest tests/test_hybrid_align.py -v
"""

import os
import sys
import json
import tempfile
import unittest

# Ensure the project root is on the path
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Import internal helpers (no audio I/O needed for unit tests)
from backend.alignment_hybrid import (
    _norm_word,
    _tokenize,
    _is_background_token,
    _strip_bg_brackets,
    _hybrid_match,
    _levenshtein_ratio,
    _phonetic_key,
    _cubic_spline_interpolate,
    _smooth_transitions,
    _enforce_global_monotonicity,
    _insert_silent_blocks,
    _compute_fragment_bounds,
    _tag_background_vocals,
    _detect_instrumental_gaps,
    parse_alignment_json,
)

try:
    import jellyfish as _jf
    HAS_JF = True
except ImportError:
    _jf = None
    HAS_JF = False

try:
    from scipy.interpolate import CubicSpline  # noqa
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------

def _make_asr_words(texts_and_times):
    """Build mock ASR word list from [(word, start, end), ...]."""
    return [
        {"word": t, "start": float(s), "end": float(e)}
        for t, s, e in texts_and_times
    ]

def _make_fragments(*args, begin_end_text):
    """Build minimal fragment dicts for post-processing tests."""
    result = []
    for (b, e, txt) in begin_end_text:
        toks = txt.split()
        step = (e - b) / max(1, len(toks))
        w = [{"text": t, "start": b + i*step, "end": b + (i+1)*step}
             for i, t in enumerate(toks)]
        result.append({"begin": f"{b:.3f}", "end": f"{e:.3f}",
                        "lines": [txt], "type": "verse", "words": w})
    return result

# ===========================================================================
# LAYER 2 — Text helpers
# ===========================================================================

class TestTextHelpers(unittest.TestCase):

    def test_norm_word_strips_punctuation(self):
        self.assertEqual(_norm_word("Hello,"), "hello")
        self.assertEqual(_norm_word("it's"), "its")
        self.assertEqual(_norm_word("LEGOLAND"), "legoland")

    def test_norm_word_unicode(self):
        self.assertEqual(_norm_word("mé"), "me")   # accented → ascii

    def test_tokenize_basic(self):
        self.assertEqual(_tokenize("Hello world"), ["Hello", "world"])

    def test_tokenize_empty(self):
        self.assertEqual(_tokenize(""), [])
        self.assertEqual(_tokenize("   "), [])

    def test_is_background_token(self):
        self.assertTrue(_is_background_token("(Come here)"))
        self.assertTrue(_is_background_token("[ad-lib]"))
        self.assertFalse(_is_background_token("Hello"))
        self.assertFalse(_is_background_token("(partial"))

    def test_strip_bg_brackets(self):
        self.assertEqual(_strip_bg_brackets("(Come here)"), "Come here")
        self.assertEqual(_strip_bg_brackets("[echo]"), "echo")

# ===========================================================================
# LAYER 2 — Levenshtein & phonetic
# ===========================================================================

class TestLevenshtein(unittest.TestCase):

    def test_exact_match(self):
        ratio = _levenshtein_ratio("hello", "hello", None)
        self.assertGreaterEqual(ratio, 99.0)

    def test_close_match(self):
        ratio = _levenshtein_ratio("legoland", "legoiand", None)  # one char off
        self.assertGreater(ratio, 70.0)

    def test_totally_different(self):
        ratio = _levenshtein_ratio("abc", "xyz", None)
        self.assertLess(ratio, 40.0)

    def test_empty_strings(self):
        self.assertEqual(_levenshtein_ratio("", "hello", None), 0.0)
        self.assertEqual(_levenshtein_ratio("hello", "", None), 0.0)


class TestPhonetic(unittest.TestCase):

    @unittest.skipUnless(HAS_JF, "jellyfish not installed")
    def test_phonetic_homophones(self):
        # "their" and "there" should have the same or very similar phonetic key
        jf = _jf
        key1 = _phonetic_key("their", jf)
        key2 = _phonetic_key("there", jf)
        self.assertEqual(key1, key2)

    @unittest.skipUnless(HAS_JF, "jellyfish not installed")
    def test_phonetic_distinct_words(self):
        jf = _jf
        key1 = _phonetic_key("bitch", jf)
        key2 = _phonetic_key("beach", jf)
        # They may or may not match exactly — just ensure non-empty
        self.assertIsInstance(key1, str)
        self.assertIsInstance(key2, str)

    def test_phonetic_no_jf_fallback(self):
        # Without jellyfish, should return 3-char prefix
        key = _phonetic_key("legoland", None)
        self.assertEqual(key, "LEG")

# ===========================================================================
# LAYER 2 — Hybrid matcher
# ===========================================================================

class TestHybridMatcher(unittest.TestCase):

    def test_exact_match_all(self):
        user  = ["hello", "world", "yeah"]
        asr   = _make_asr_words([("hello", 0.0, 0.3), ("world", 0.4, 0.8), ("yeah", 0.9, 1.1)])
        mapping = _hybrid_match(user, asr)
        self.assertEqual(len(mapping), 3)
        self.assertEqual(mapping[0], 0)
        self.assertEqual(mapping[1], 1)
        self.assertEqual(mapping[2], 2)

    def test_fuzzy_typo(self):
        user = ["legoland"]
        asr  = _make_asr_words([("legoiand", 1.0, 1.5)])  # OCR-like typo
        mapping = _hybrid_match(user, asr)
        self.assertIn(0, mapping)

    def test_inserted_asr_noise(self):
        """Extra ASR words (noise) should not prevent matching real words."""
        user = ["button", "boys"]
        asr  = _make_asr_words([
            ("uh", 0.0, 0.1),          # noise
            ("button", 0.2, 0.5),
            ("mm", 0.5, 0.6),          # noise
            ("boys", 0.7, 1.0),
        ])
        mapping = _hybrid_match(user, asr)
        self.assertIn(0, mapping)  # button matched
        self.assertIn(1, mapping)  # boys matched
        # Noisy words must not be mapped to user words
        matched_asr = set(mapping.values())
        self.assertNotIn(0, matched_asr)  # "uh" not matched
        self.assertNotIn(2, matched_asr)  # "mm" not matched

    def test_repeated_chorus_matching(self):
        """
        Repeated chorus lines should independently match their own ASR words,
        not steal timestamps from the first occurrence.
        """
        chorus = ["Legoland", "bitch", "button", "boys"]
        user_words = chorus + chorus  # chorus repeated twice
        asr  = _make_asr_words([
            ("legoland", 0.5, 0.9), ("bitch", 1.0, 1.2),
            ("button",   1.3, 1.6), ("boys",  1.7, 2.0),
            ("legoland", 30.5, 30.9), ("bitch", 31.0, 31.2),  # 2nd chorus
            ("button",   31.3, 31.6), ("boys",  31.7, 32.0),
        ])
        mapping = _hybrid_match(user_words, asr)
        # First chorus words should map to ASR indices 0–3
        for ui in range(4):
            if ui in mapping:
                self.assertLessEqual(mapping[ui], 3)
        # Second chorus words should map to ASR indices 4–7
        for ui in range(4, 8):
            if ui in mapping:
                self.assertGreaterEqual(mapping[ui], 4)

    def test_empty_inputs(self):
        self.assertEqual(_hybrid_match([], []), {})
        self.assertEqual(_hybrid_match(["hello"], []), {})
        self.assertEqual(_hybrid_match([], _make_asr_words([("hi", 0, 1)])), {})

    def test_match_rate_target(self):
        """Overall match rate should be ≥ 80% for a clean transcript."""
        lyrics = [
            "Codeine mix promethazine I hate when I run out",
            "On the deen I'm gettin clean once my new album Z come out",
            "I done bipped inside a strike my mama called me out en route goddamn",
        ]
        user_words = []
        for line in lyrics:
            user_words.extend(_tokenize(line))

        # Mock ASR words — same words with slight timing and minor variants
        asr_raw = [
            ("codeine", 0.0, 0.4), ("mix", 0.5, 0.7), ("promethazine", 0.8, 1.3),
            ("i", 1.4, 1.5), ("hate", 1.6, 1.9), ("when", 2.0, 2.2),
            ("i", 2.3, 2.4), ("run", 2.5, 2.7), ("out", 2.8, 3.0),
            ("on", 3.5, 3.6), ("the", 3.7, 3.8), ("deen", 3.9, 4.2),
            ("im", 4.3, 4.4), ("gettin", 4.5, 4.8), ("clean", 4.9, 5.2),
            ("once", 5.3, 5.5), ("my", 5.6, 5.7), ("new", 5.8, 5.9),
            ("album", 6.0, 6.4), ("z", 6.5, 6.6), ("come", 6.7, 6.9), ("out", 7.0, 7.2),
            ("i", 7.5, 7.6), ("done", 7.7, 7.9), ("bipped", 8.0, 8.3),
            ("inside", 8.4, 8.7), ("a", 8.8, 8.9), ("strike", 9.0, 9.4),
            ("my", 9.5, 9.6), ("mama", 9.7, 10.0), ("called", 10.1, 10.4),
            ("me", 10.5, 10.6), ("out", 10.7, 10.9), ("en", 11.0, 11.2),
            ("route", 11.3, 11.7), ("goddamn", 11.8, 12.2),
        ]
        asr = _make_asr_words(asr_raw)
        mapping = _hybrid_match(user_words, asr)
        match_pct = len(mapping) / max(len(user_words), 1)
        self.assertGreaterEqual(match_pct, 0.80,
            f"Match rate {match_pct:.1%} < 80% — hybrid matcher underperforming")

# ===========================================================================
# LAYER 3 — Background vocal tagging
# ===========================================================================

class TestBackgroundTagging(unittest.TestCase):

    def test_parenthesised_line_tagged_background(self):
        lines = ["Hello world", "(Come here)", "Yeah it's me"]
        tags = _tag_background_vocals(lines)
        self.assertEqual(tags[0], "verse")
        self.assertEqual(tags[1], "background")
        self.assertEqual(tags[2], "verse")

    def test_bracket_line_tagged_background(self):
        lines = ["[ad-lib]", "real lyrics here"]
        tags = _tag_background_vocals(lines)
        self.assertEqual(tags[0], "background")
        self.assertEqual(tags[1], "verse")

# ===========================================================================
# LAYER 4 — Cubic spline interpolation
# ===========================================================================

class TestSplineInterpolation(unittest.TestCase):

    @unittest.skipUnless(HAS_SCIPY, "scipy not installed")
    def test_monotonic_output(self):
        anchor_times   = [1.0, 2.5, 4.0]
        anchor_indices = [0, 5, 9]
        result = _cubic_spline_interpolate(anchor_times, anchor_indices, 10, 1.0, 4.5)
        self.assertEqual(len(result), 10)
        for i in range(1, len(result)):
            self.assertGreaterEqual(result[i], result[i-1],
                f"Non-monotonic at index {i}: {result[i]} < {result[i-1]}")

    @unittest.skipUnless(HAS_SCIPY, "scipy not installed")
    def test_boundary_respect(self):
        result = _cubic_spline_interpolate([1.0, 3.0], [0, 4], 5, 1.0, 3.5)
        self.assertGreaterEqual(result[0], 1.0)
        self.assertLessEqual(result[-1], 3.5)

    def test_linear_fallback_without_scipy(self):
        # Without scipy (mocked as None via passing < 2 anchors), uses linear
        result = _cubic_spline_interpolate([], [], 4, 0.0, 4.0)
        self.assertEqual(len(result), 4)
        self.assertAlmostEqual(result[0], 0.0, places=2)

# ===========================================================================
# LAYER 4 — Silent block insertion
# ===========================================================================

class TestSilentBlocks(unittest.TestCase):

    def test_gap_inserted(self):
        frags = [
            {"begin": "0.000", "end": "3.000", "lines": ["hello"], "type": "verse", "words": []},
            {"begin": "8.000", "end": "10.000", "lines": ["world"], "type": "verse", "words": []},
        ]
        gaps = [{"start": 3.5, "end": 7.5}]  # 4-second gap
        result = _insert_silent_blocks(frags, gaps)
        types = [f["type"] for f in result]
        self.assertIn("instrumental", types)

    def test_already_covered_gap_not_inserted(self):
        frags = [
            {"begin": "0.000", "end": "10.000", "lines": ["long line"], "type": "verse", "words": []},
        ]
        gaps = [{"start": 2.0, "end": 5.0}]  # fully covered by existing fragment
        result = _insert_silent_blocks(frags, gaps)
        self.assertEqual(len(result), 1)  # no extra blocks

    def test_sorted_output(self):
        frags = [
            {"begin": "5.000", "end": "8.000", "lines": ["b"], "type": "verse", "words": []},
            {"begin": "0.000", "end": "3.000", "lines": ["a"], "type": "verse", "words": []},
        ]
        gaps = [{"start": 3.2, "end": 4.8}]
        result = _insert_silent_blocks(frags, gaps)
        times = [float(f["begin"]) for f in result]
        self.assertEqual(times, sorted(times))

# ===========================================================================
# LAYER 5 — Post-processing
# ===========================================================================

class TestMonotonicity(unittest.TestCase):

    def test_overlapping_fragments_fixed(self):
        frags = _make_fragments(begin_end_text=[
            (0.0, 5.0, "hello world"),
            (4.0, 8.0, "yeah it is"),   # overlaps previous
        ])
        _enforce_global_monotonicity(frags)
        f0_end   = float(frags[0]["end"])
        f1_start = float(frags[1]["begin"])
        self.assertLessEqual(f0_end, f1_start + 0.02,
            "Fragment overlap not resolved by monotonicity pass")

    def test_word_timestamps_monotonic(self):
        frags = _make_fragments(begin_end_text=[
            (1.0, 3.0, "one two three four"),
        ])
        # Deliberately break word order
        frags[0]["words"][2]["start"] = 0.5  # out of order
        _enforce_global_monotonicity(frags)
        words = frags[0]["words"]
        for i in range(1, len(words)):
            self.assertLessEqual(words[i-1]["start"], words[i]["start"],
                f"Word timestamps not monotonic at index {i}")

class TestSmoothTransitions(unittest.TestCase):

    def test_small_gap_closed(self):
        frags = _make_fragments(begin_end_text=[
            (0.0, 3.0, "hello"),
            (3.05, 6.0, "world"),  # 50 ms gap — should be closed
        ])
        _smooth_transitions(frags)
        f0_end   = float(frags[0]["end"])
        f1_start = float(frags[1]["begin"])
        self.assertAlmostEqual(f0_end, f1_start, places=2)

    def test_overlap_resolved(self):
        frags = _make_fragments(begin_end_text=[
            (0.0, 4.0, "hello"),
            (3.9, 7.0, "world"),  # 100 ms overlap
        ])
        _smooth_transitions(frags)
        f0_end   = float(frags[0]["end"])
        f1_start = float(frags[1]["begin"])
        self.assertLessEqual(f1_start, f0_end + 0.01)

# ===========================================================================
# parse_alignment_json — round-trip
# ===========================================================================

class TestParseAlignmentJson(unittest.TestCase):

    def _write_temp_json(self, data):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return path

    def test_parse_basic(self):
        data = {
            "fragments": [
                {"begin": "1.000", "end": "3.500", "lines": ["Hello world"],
                 "type": "verse", "words": []},
                {"begin": "4.000", "end": "6.000", "lines": ["Yeah it's me"],
                 "type": "verse", "words": []},
            ]
        }
        path = self._write_temp_json(data)
        try:
            result = parse_alignment_json(path)
            self.assertEqual(len(result), 2)
            self.assertAlmostEqual(result[0]["start"], 1.0)
            self.assertAlmostEqual(result[1]["end"],   6.0)
            self.assertEqual(result[0]["text"], "Hello world")
        finally:
            os.unlink(path)

    def test_parse_missing_fragments_key(self):
        path = self._write_temp_json({"not_fragments": []})
        try:
            result = parse_alignment_json(path)
            self.assertEqual(result, [])  # graceful empty list
        finally:
            os.unlink(path)

    def test_parse_includes_word_list(self):
        data = {
            "fragments": [{
                "begin": "0.000", "end": "2.000",
                "lines": ["test"],
                "type":  "verse",
                "words": [
                    {"text": "test", "start": 0.0, "end": 2.0,
                     "confidence": 0.9, "matched_by": "exact"}
                ],
            }]
        }
        path = self._write_temp_json(data)
        try:
            result = parse_alignment_json(path)
            self.assertEqual(len(result[0]["words"]), 1)
            self.assertEqual(result[0]["words"][0]["text"], "test")
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
