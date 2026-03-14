# core/frustration_scorer.py
# Computes a frustration score in [0, 1] from sentiment analysis output
#
# Revised formula — more realistic mapping:
#   Neutral sentiment (0.0) → frustration 0.3  (not 0.5)
#   Mildly negative (-0.3)  → frustration ~0.45 (mild, not moderate)
#   Very negative (-0.8)    → frustration ~0.75 (high, triggers handover)
#   Extremely negative (-1) → frustration ~0.85 (critical)
#
# This prevents calm/neutral messages from falsely triggering alerts.

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    FRUSTRATION_ALERT_THRESHOLD,
    FRUSTRATION_HANDOVER_THRESHOLD,
    FRUSTRATION_CRITICAL_THRESHOLD
)


def compute_frustration(sentiment_score: float, signal_boost: float = 0.0) -> dict:
    """
    Compute frustration score from a sentiment score.

    Args:
        sentiment_score: float in [-1, 1] from sentiment engine
        signal_boost: float in [0, 0.25] from emotional signal features (CAPS, !!!)

    Returns:
        dict with:
            - 'raw_frustration': formula result before boost
            - 'frustration_score': final clamped score [0, 1]
            - 'level': str category
            - 'alert': bool
            - 'handover': bool
    """
    # Revised formula — shifts the neutral point down from 0.5 to 0.3
    # so casual complaints don't falsely trigger handover
    #
    # sentiment +1.0  → frustration 0.05  (very positive = very calm)
    # sentiment  0.0  → frustration 0.30  (neutral = low frustration)
    # sentiment -0.5  → frustration 0.55  (mildly negative = moderate)
    # sentiment -0.8  → frustration 0.72  (very negative = high)
    # sentiment -1.0  → frustration 0.85  (extremely negative = critical)

    # Step 1: base score — compress the upper range so neutral doesn't hit 0.5
    base = 0.30 - (sentiment_score * 0.55)

    # Step 2: add emotional signal boost (CAPS, !!!, intensifiers)
    boosted = base + signal_boost

    # Step 3: clamp to [0, 1]
    frustration = max(0.0, min(1.0, boosted))

    level    = _categorize(frustration)
    alert    = frustration >= FRUSTRATION_ALERT_THRESHOLD
    handover = frustration >= FRUSTRATION_HANDOVER_THRESHOLD

    return {
        "raw_frustration":  round(base, 4),
        "frustration_score": round(frustration, 4),
        "level":    level,
        "alert":    alert,
        "handover": handover
    }


def _categorize(score: float) -> str:
    if score < 0.25:
        return "calm"
    elif score < FRUSTRATION_ALERT_THRESHOLD:
        return "mild"
    elif score < FRUSTRATION_HANDOVER_THRESHOLD:
        return "moderate"
    elif score < FRUSTRATION_CRITICAL_THRESHOLD:
        return "high"
    else:
        return "critical"


def frustration_to_bar(score: float, width: int = 20) -> str:
    filled = int(score * width)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {score:.2f}"


