# core/sentiment_engine.py
# Multi-level sentiment analysis engine
# Combines VADER (lexicon-based, fast) with RoBERTa (transformer-based, deep)
# Weighted ensemble as specified in config.py

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from models.model_loader import predict_sentiment
from utils.preprocessor import preprocess, compute_signal_boost
from config import ROBERTA_WEIGHT, VADER_WEIGHT

_vader = None


def _get_vader():
    global _vader
    if _vader is None:
        _vader = SentimentIntensityAnalyzer()
    return _vader


def analyse(text: str) -> dict:
    """
    Full sentiment analysis on a user message.
    Combines VADER + RoBERTa into a single ensemble sentiment score.

    Args:
        text: raw user message string

    Returns:
        dict with:
            - 'sentiment_score': float [-1, 1] (ensemble)
            - 'vader_score': float [-1, 1]
            - 'roberta_score': float [-1, 1]
            - 'roberta_label': str
            - 'signal_boost': float [0, 0.25]
            - 'features': dict of emotional signals
            - 'clean_text': normalized text used for model
    """
    # Step 1: Preprocess
    processed = preprocess(text)
    clean_text = processed["clean_text"]
    features = processed["features"]
    signal_boost = compute_signal_boost(features)

    # Step 2: VADER score (compound: -1 to +1)
    vader_result = _get_vader().polarity_scores(clean_text)
    vader_score = vader_result["compound"]  # Already in [-1, 1]

    # Step 3: RoBERTa score
    roberta_result = predict_sentiment(clean_text)
    roberta_score = roberta_result["sentiment_score"]
    roberta_label = roberta_result["label"]

    # Step 4: Weighted ensemble
    ensemble_score = (ROBERTA_WEIGHT * roberta_score) + (VADER_WEIGHT * vader_score)
    ensemble_score = max(-1.0, min(1.0, ensemble_score))

    return {
        "sentiment_score": round(ensemble_score, 4),
        "vader_score": round(vader_score, 4),
        "roberta_score": round(roberta_score, 4),
        "roberta_label": roberta_label,
        "roberta_class_scores": roberta_result["scores"],
        "signal_boost": round(signal_boost, 4),
        "features": features,
        "clean_text": clean_text
    }
