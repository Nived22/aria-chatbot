import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from config import SENTIMENT_MODEL, DEVICE

_tokenizer = None
_model     = None
_label_map = None

# Path to your fine-tuned model saved after training
_TRAINED_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "saved", "sentiment_model"
)


def _trained_model_exists() -> bool:
    """Check if fine-tuned model has been saved."""
    return os.path.exists(os.path.join(_TRAINED_MODEL_PATH, "config.json"))


def load_model():
    """
    Load sentiment model and tokenizer.
    Uses fine-tuned model if available, otherwise pretrained.
    Cached after first call.
    """
    global _tokenizer, _model, _label_map

    if _model is not None:
        return _tokenizer, _model, _label_map

    # ── Use fine-tuned model if it exists ────────────────────────────────────
    if _trained_model_exists():
        model_path = _TRAINED_MODEL_PATH
        print(f"[ModelLoader] ✅ Loading YOUR fine-tuned model from {model_path}")
    else:
        model_path = SENTIMENT_MODEL
        print(f"[ModelLoader] Loading pretrained model: {model_path}")
        print(f"[ModelLoader] Tip: Run 02_model_training.ipynb to train your own model")

    _tokenizer = AutoTokenizer.from_pretrained(model_path)
    _model     = AutoModelForSequenceClassification.from_pretrained(model_path)
    _model.to(DEVICE)
    _model.eval()

    raw_labels = _model.config.id2label
    _label_map = {int(k): v.lower() for k, v in raw_labels.items()}

    print(f"[ModelLoader] Ready. Labels: {_label_map}")
    return _tokenizer, _model, _label_map


def predict_sentiment(text: str) -> dict:
    """
    Run sentiment classification on a single text.
    Returns label, scores, and sentiment_score in [-1, 1].
    """
    tokenizer, model, label_map = load_model()

    inputs = tokenizer(
        text, return_tensors="pt",
        truncation=True, max_length=512, padding=True
    ).to(DEVICE)

    with torch.no_grad():
        outputs = model(**inputs)
        probs   = torch.nn.functional.softmax(outputs.logits, dim=-1)
        probs   = probs.squeeze().cpu().tolist()

    scores = {label_map[i]: probs[i] for i in range(len(probs))}

    predicted_idx   = int(torch.tensor(probs).argmax())
    predicted_label = label_map[predicted_idx]

    pos_prob = scores.get("positive", scores.get("pos", 0.0))
    neg_prob = scores.get("negative", scores.get("neg", 0.0))
    neu_prob = scores.get("neutral",  scores.get("neu", 0.0))

    sentiment_score = (pos_prob * 1.0) + (neu_prob * 0.0) + (neg_prob * -1.0)
    sentiment_score = max(-1.0, min(1.0, sentiment_score))

    return {
        "label":           predicted_label,
        "scores":          scores,
        "sentiment_score": round(sentiment_score, 4)
    }
