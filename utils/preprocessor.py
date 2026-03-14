# utils/preprocessor.py
# Text preprocessing layer
# Preserves emotional signals (!!!,  CAPS, emojis) as they are features for frustration detection

import re
import unicodedata


def preprocess(text: str) -> dict:
    """
    Preprocess a user message for sentiment analysis.
    Returns both cleaned text AND extracted emotional signal features.

    Args:
        text: Raw user message

    Returns:
        dict with:
            - 'clean_text': normalized text for model input
            - 'features': dict of extracted emotional signals
    """
    features = extract_emotional_signals(text)
    clean = normalize_text(text)
    return {"clean_text": clean, "features": features}


def normalize_text(text: str) -> str:
    """Normalize text while preserving emotional content."""
    # Normalize unicode (handles accented chars etc.)
    text = unicodedata.normalize("NFKC", text)
    # Collapse multiple spaces
    text = re.sub(r" {2,}", " ", text)
    # Collapse excessive newlines
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def extract_emotional_signals(text: str) -> dict:
    """
    Extract emotional signal features from raw text.
    These features are used to boost/adjust the frustration score.

    Features detected:
        - exclamation_count: number of ! characters
        - question_mark_count: number of ? characters
        - all_caps_words: count of ALL CAPS words (≥3 chars)
        - repeated_punctuation: True if !! or ??? detected
        - has_negative_intensifiers: True if words like NEVER, WORST, HORRIBLE
        - emoji_count: rough count of emoji characters
        - word_count: total word count
        - avg_word_length: average word length (short = informal/angry)
    """
    features = {}

    # Punctuation signals
    features["exclamation_count"] = text.count("!")
    features["question_mark_count"] = text.count("?")
    features["repeated_punctuation"] = bool(re.search(r"[!?]{2,}", text))

    # CAPS signals (words ≥ 3 chars in all caps = shouting)
    words = text.split()
    caps_words = [w for w in words if w.isupper() and len(w) >= 3 and w.isalpha()]
    features["all_caps_words"] = len(caps_words)

    # Negative intensifiers
    intensifiers = {
        "never", "worst", "horrible", "disgusting", "outrageous",
        "unacceptable", "ridiculous", "pathetic", "useless", "terrible",
        "awful", "absurd", "incompetent", "furious", "livid", "disgusted"
    }
    lowered = text.lower()
    features["has_negative_intensifiers"] = any(word in lowered for word in intensifiers)

    # Emoji count (rough: count chars outside ASCII range that aren't accented letters)
    emoji_chars = [c for c in text if ord(c) > 8000]
    features["emoji_count"] = len(emoji_chars)

    # Basic text stats
    features["word_count"] = len(words)
    if words:
        features["avg_word_length"] = sum(len(w) for w in words) / len(words)
    else:
        features["avg_word_length"] = 0.0

    return features


def compute_signal_boost(features: dict) -> float:
    """
    Convert emotional signals into a small frustration score boost (+0.0 to +0.25).
    This is added on top of the model-predicted frustration score.

    Args:
        features: dict from extract_emotional_signals()

    Returns:
        boost value between 0.0 and 0.25
    """
    boost = 0.0

    if features.get("repeated_punctuation"):
        boost += 0.08
    if features.get("exclamation_count", 0) >= 2:
        boost += 0.05
    if features.get("all_caps_words", 0) >= 1:
        boost += 0.07
    if features.get("has_negative_intensifiers"):
        boost += 0.08
    if features.get("emoji_count", 0) > 0:
        boost += 0.02  # emojis can be positive or negative — small boost only

    # Cap boost at 0.25
    return min(boost, 0.25)
