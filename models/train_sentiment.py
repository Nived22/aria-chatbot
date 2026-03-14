# models/train_sentiment.py
# Phase 1 Training: Fine-tune RoBERTa on IberaSoft/ecommerce-reviews-sentiment
# Run from project root: python models/train_sentiment.py
# Saves checkpoint to models/saved/sentiment_model/

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import torch
from transformers import (
    AutoTokenizer, AutoModelForSequenceClassification,
    TrainingArguments, Trainer
)
from datasets import load_dataset
from sklearn.metrics import accuracy_score, f1_score
import numpy as np
from config import SENTIMENT_MODEL, DEVICE

SAVE_PATH = os.path.join(os.path.dirname(__file__), "saved", "sentiment_model")
os.makedirs(SAVE_PATH, exist_ok=True)

NUM_LABELS = 3   # negative, neutral, positive
BATCH_SIZE = 16
EPOCHS = 3
MAX_LEN = 128


def tokenize(examples, tokenizer):
    return tokenizer(examples["text"], truncation=True,
                     padding="max_length", max_length=MAX_LEN)


def compute_metrics(eval_pred):
    logits, labels = eval_pred
    preds = np.argmax(logits, axis=-1)
    return {
        "accuracy": accuracy_score(labels, preds),
        "f1_macro": f1_score(labels, preds, average="macro")
    }


def train():
    print(f"[Train-Phase1] Loading model: {SENTIMENT_MODEL}")
    tokenizer = AutoTokenizer.from_pretrained(SENTIMENT_MODEL)
    model = AutoModelForSequenceClassification.from_pretrained(
        SENTIMENT_MODEL, num_labels=NUM_LABELS, ignore_mismatched_sizes=True
    )
    model.to(DEVICE)

    print("[Train-Phase1] Loading dataset...")
    ds = load_dataset("IberaSoft/ecommerce-reviews-sentiment")
    # Ensure train/test split exists
    if "test" not in ds:
        ds = ds["train"].train_test_split(test_size=0.1, seed=42)

    tokenized = ds.map(lambda x: tokenize(x, tokenizer), batched=True)
    tokenized = tokenized.rename_column("label", "labels")
    tokenized.set_format("torch", columns=["input_ids", "attention_mask", "labels"])

    args = TrainingArguments(
        output_dir=SAVE_PATH,
        num_train_epochs=EPOCHS,
        per_device_train_batch_size=BATCH_SIZE,
        per_device_eval_batch_size=BATCH_SIZE,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1_macro",
        logging_steps=50,
        fp16=torch.cuda.is_available(),
        report_to="none"
    )

    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=tokenized["train"],
        eval_dataset=tokenized["test"],
        compute_metrics=compute_metrics
    )

    print("[Train-Phase1] Starting training...")
    trainer.train()
    trainer.save_model(SAVE_PATH)
    tokenizer.save_pretrained(SAVE_PATH)
    print(f"[Train-Phase1] Saved to {SAVE_PATH}")

    results = trainer.evaluate()
    print(f"[Train-Phase1] Final eval: {results}")
    return results


if __name__ == "__main__":
    train()
