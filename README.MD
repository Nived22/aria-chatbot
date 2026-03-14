System Architecture
User Message
     ↓
Text Preprocessor
     ↓
Sentiment Engine (VADER + RoBERTa)  →  Sentiment Score [-1, 1]
     ↓
Frustration Scorer                  →  Frustration Score [0, 1]
     ↓
Trend Tracker                       →  Emotion Trajectory
     ↓
Response Manager
  ├── Score < 0.5  → Normal response
  ├── Score 0.5–0.7 → Empathetic response + alert agent
  └── Score ≥ 0.7  → Human handover
     ↓
Logger (session logs → logs/)

Models Used

VADER — Fast lexicon-based baseline (no GPU needed)
cardiffnlp/twitter-roberta-base-sentiment-latest — RoBERTa fine-tuned for sentiment
bert-base-uncased — Optional BERT backbone (swappable in config.py)