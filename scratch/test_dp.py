import sys
sys.path.append('backend')
from alignment_whisperx import COST_MISMATCH, COST_SKIP_ASR, COST_MISS_USER, COST_MATCH, COST_PARTIAL, _norm_word

def _dp_match_debug(user_words, asr_words):
    n = len(user_words)
    m = len(asr_words)
    if n == 0 or m == 0:
        return {}

    INF = 1e9
    dp = [[INF] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0
    for i in range(1, n + 1):
        dp[i][0] = dp[i - 1][0] + COST_MISS_USER
    for j in range(1, m + 1):
        dp[0][j] = dp[0][j - 1] + COST_SKIP_ASR

    for i in range(1, n + 1):
        uw = _norm_word(user_words[i - 1])
        for j in range(1, m + 1):
            aw = _norm_word(asr_words[j - 1].get("word", ""))
            if uw and aw and uw == aw:
                sub = COST_MATCH
            elif uw and aw and min(len(uw), len(aw)) >= 3 and (uw in aw or aw in uw):
                sub = COST_PARTIAL
            else:
                sub = COST_MISMATCH
            dp[i][j] = min(
                dp[i - 1][j - 1] + sub,
                dp[i - 1][j] + COST_MISS_USER,
                dp[i][j - 1] + COST_SKIP_ASR,
            )

    mapping = {}
    i, j = n, m
    while i > 0 and j > 0:
        uw = _norm_word(user_words[i - 1])
        aw = _norm_word(asr_words[j - 1].get("word", ""))
        if uw and aw and uw == aw:
            sub = COST_MATCH
        elif uw and aw and min(len(uw), len(aw)) >= 3 and (uw in aw or aw in uw):
            sub = COST_PARTIAL
        else:
            sub = COST_MISMATCH
        
        print(f"At i={i} '{uw}', j={j} '{aw}': dp={dp[i][j]}, sub={sub}, match_cost={dp[i-1][j-1]+sub}, drop_u={dp[i-1][j]+COST_MISS_USER}, drop_a={dp[i][j-1]+COST_SKIP_ASR}")
        if abs(dp[i][j] - (dp[i - 1][j - 1] + sub)) < 1e-9 and sub <= COST_PARTIAL:
            print("  -> Chose MATCH/PARTIAL")
            mapping[i - 1] = j - 1
            i -= 1; j -= 1
        elif abs(dp[i][j] - (dp[i - 1][j] + COST_MISS_USER)) < 1e-9:
            print("  -> Chose DROP USER")
            i -= 1
        else:
            print("  -> Chose DROP ASR")
            j -= 1
    return mapping

user_words = ["hello", "world", "this", "is", "a", "test", "extra"]
asr_words = [{"word": "hello"}, {"word": "world"}, {"word": "that"}, {"word": "is"}, {"word": "test"}, {"word": "noise"}, {"word": "extra"}]

mapping = _dp_match_debug(user_words, asr_words)
