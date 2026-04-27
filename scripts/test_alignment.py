from backend.alignment_hybrid import align

# The original audio
audio_path = "uploads/20260417_141917_audio_normalized.wav"
# The original plain-text lyrics input
lyrics_path = "uploads/20260417_141917_lyrics.txt"
output_json = "alignments/hybrid_test_output.json"

out = align(audio_path, lyrics_path, output_json, language="en")
print(f"Generated alignment at {out}")
