# utils/input_validator.py
# Validates user input before it enters the NLP pipeline
# Catches: random gibberish, keyboard smashing, single characters,
#          overly short inputs, repeated characters, non-English spam

import re
import math
from collections import Counter


# ── Common real English words — if input contains any of these it's valid ─────
_REAL_WORDS = {
    "hi","hey","hello","help","order","late","missing","refund","return",
    "cancel","delivery","track","package","item","product","money","paid",
    "buy","bought","wrong","broken","damaged","account","login","password",
    "please","thanks","thank","sorry","when","where","what","how","why","can",
    "need","want","get","have","not","arrived","delivered","received","waiting",
    "issue","problem","complaint","urgent","angry","frustrated","unhappy","bad",
    "good","okay","fine","yes","no","my","your","the","and","but","for","is",
    "are","was","been","will","did","does","still","now","today","week","days",
    "never","always","again","back","give","take","send","check","fix","sort",
    "status","update","information","support","service","customer","wrong",
    "i","me","we","you","it","this","that","they","them","our","their",
}


def _character_entropy(text: str) -> float:
    """Shannon entropy of character distribution. Real words have entropy 3.0+"""
    if not text:
        return 0.0
    counts = Counter(text.lower())
    total  = len(text)
    return -sum((c/total) * math.log2(c/total) for c in counts.values())


def _vowel_ratio(text: str) -> float:
    """Real English words have ~35-45% vowels."""
    letters = [c for c in text.lower() if c.isalpha()]
    if not letters:
        return 0.0
    vowels = sum(1 for c in letters if c in "aeiou")
    return vowels / len(letters)


def _longest_consonant_run(text: str) -> int:
    """Real words rarely have more than 3 consonants in a row."""
    consonants = set("bcdfghjklmnpqrstvwxyz")
    max_run, run = 0, 0
    for c in text.lower():
        if c in consonants:
            run += 1
            max_run = max(max_run, run)
        else:
            run = 0
    return max_run


def validate_input(message: str) -> dict:
    """
    Validate whether user input is meaningful.

    Returns:
        {
            'valid': bool,
            'reason': str,           # why it's invalid (empty if valid)
            'reply': str | None      # suggested reply to show user (if invalid)
        }
    """
    if not message or not message.strip():
        return {
            "valid": False,
            "reason": "empty",
            "reply": "It looks like your message was empty — what can I help you with?"
        }

    text  = message.strip()
    words = text.split()
    clean = re.sub(r"[^a-zA-Z\s]", "", text).strip()
    alpha_words = [w.lower() for w in words if re.sub(r"[^a-zA-Z]", "", w)]

    # ── 1. Too short ──────────────────────────────────────────────────────────
    if len(text) < 2:
        return {
            "valid": False,
            "reason": "too_short",
            "reply": "Could you tell me a bit more? I want to make sure I help you properly."
        }

    # ── 2. Pure numbers / symbols ─────────────────────────────────────────────
    if not any(c.isalpha() for c in text):
        return {
            "valid": False,
            "reason": "no_letters",
            "reply": "I didn't quite catch that — could you describe what you need help with?"
        }

    # ── 3. Single repeated character e.g. "aaaaaaa", "!!!!!!" ────────────────
    unique_chars = set(text.lower().replace(" ", ""))
    if len(unique_chars) <= 2 and len(text) > 3:
        return {
            "valid": False,
            "reason": "repeated_chars",
            "reply": "I didn't quite understand that. Could you rephrase what you need help with?"
        }

    # ── 4. Check if any real words are present — if yes, always valid ─────────
    words_lower = set(re.sub(r"[^a-zA-Z\s]", " ", text.lower()).split())
    if words_lower & _REAL_WORDS:
        return {"valid": True, "reason": "", "reply": None}

    # ── 5. Gibberish detection (only for purely alphabetic inputs) ────────────
    if clean and len(alpha_words) > 0:
        avg_word_len  = sum(len(w) for w in alpha_words) / len(alpha_words)
        entropy       = _character_entropy(clean.replace(" ", ""))
        vowel_r       = _vowel_ratio(clean)
        consonant_run = _longest_consonant_run(clean.replace(" ", ""))

        # Flag as gibberish if multiple signals agree
        gibberish_signals = 0
        if vowel_r < 0.15:           gibberish_signals += 1  # barely any vowels
        if consonant_run >= 5:        gibberish_signals += 1  # long consonant run
        if entropy < 2.5 and len(clean.replace(" ","")) > 6:
                                      gibberish_signals += 1  # low character variety
        if avg_word_len > 9 and len(alpha_words) == 1:
                                      gibberish_signals += 1  # one very long weird word

        if gibberish_signals >= 2:
            return {
                "valid": False,
                "reason": "gibberish",
                "reply": "I'm not sure I understood that. Could you rephrase? For example, you can say things like 'where is my order' or 'I need a refund'."
            }

    return {"valid": True, "reason": "", "reply": None}
