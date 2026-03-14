# config.py
# Central configuration for the Emotion-Aware Chatbot System

import torch

# ─── Model Settings ──────────────────────────────────────────────────────────
SENTIMENT_MODEL = "cardiffnlp/twitter-roberta-base-sentiment-latest"
USE_GPU  = torch.cuda.is_available()
DEVICE   = "cuda" if USE_GPU else "cpu"

# ─── Frustration Thresholds ───────────────────────────────────────────────────
#
#  What each level means in plain English:
#
#  0.0 – 0.25  calm      → "hi", "thanks", normal questions
#  0.25 – 0.50 mild      → "my order is late", "I need a refund"
#  0.50 – 0.65 moderate  → "I've been waiting 2 weeks", "this is annoying"
#  0.65 – 0.80 high      → "this is unacceptable", "I'm very angry"
#  0.80+       critical  → "I WANT MY MONEY BACK NOW", repeated CAPS/!!!
#
FRUSTRATION_ALERT_THRESHOLD    = 0.50   # Agent put on standby
FRUSTRATION_HANDOVER_THRESHOLD = 0.78   # Trigger human handover (raised from 0.7)
FRUSTRATION_CRITICAL_THRESHOLD = 0.88   # Instant handover, no delay

# ─── Trend Tracking ───────────────────────────────────────────────────────────
CONSECUTIVE_TURNS_FOR_ESCALATION = 3    # 3 high turns in a row → escalate
TREND_WINDOW_SIZE                = 5    # How many past turns to track

# ─── Sentiment Engine Weights ─────────────────────────────────────────────────
ROBERTA_WEIGHT = 0.70
VADER_WEIGHT   = 0.30

# ─── Response Logic ───────────────────────────────────────────────────────────
EMPATHY_SCORE_TRIGGER      = 0.50   # Start empathetic tone above this
SIMPLIFY_LANGUAGE_TRIGGER  = 0.65   # Use shorter, calmer language above this

# ─── Data Retention ───────────────────────────────────────────────────────────
LOG_RETENTION_DAYS = 365            # 12 months — GDPR FR10
LOG_DIR            = "logs"

# ─── Session Settings ─────────────────────────────────────────────────────────
MAX_HISTORY_TURNS = 20
BOT_NAME          = "kunjappan"
COMPANY_NAME      = "kunji pidiya"


