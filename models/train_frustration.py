# models/train_frustration.py
# Phase 2+3 Training: Fine-tune RoBERTa for frustration REGRESSION [0,1]
# Uses EmoWOZ + Bitext W-tagged + Synthetic data
# Run: python models/train_frustration.py
# Saves to models/saved/frustration_model/

import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import torch
import torch.nn as nn
import numpy as np
from torch.utils.data import DataLoader, random_split
from transformers import AutoTokenizer, AutoModel, get_linear_schedule_with_warmup
from torch.optim import AdamW
from config import SENTIMENT_MODEL, DEVICE
from data.dataset_loader import (
    load_phase2_emowoz, load_phase3_bitext,
    load_synthetic, emowoz_to_frustration,
    load_phase4_twitter
)

SAVE_PATH = os.path.join(os.path.dirname(__file__), "saved", "frustration_model")
os.makedirs(SAVE_PATH, exist_ok=True)

BATCH_SIZE = 16
EPOCHS = 4
MAX_LEN = 128
LR = 2e-5


# ── Regression Model ─────────────────────────────────────────────────────────
class FrustrationRegressor(nn.Module):
    """RoBERTa backbone + regression head → frustration score [0,1]"""

    def __init__(self, base_model_path):
        super().__init__()
        self.encoder = AutoModel.from_pretrained(base_model_path)
        hidden = self.encoder.config.hidden_size
        self.regressor = nn.Sequential(
            nn.Dropout(0.1),
            nn.Linear(hidden, 128),
            nn.ReLU(),
            nn.Linear(128, 1),
            nn.Sigmoid()   # clamp output to [0,1]
        )

    def forward(self, input_ids, attention_mask):
        out = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        cls = out.last_hidden_state[:, 0, :]   # [CLS] token
        return self.regressor(cls).squeeze(-1)


# ── Dataset ──────────────────────────────────────────────────────────────────
class TextFrustrationDataset(torch.utils.data.Dataset):
    def __init__(self, texts, scores, tokenizer):
        enc = tokenizer(texts, truncation=True, padding=True,
                        max_length=MAX_LEN, return_tensors="pt")
        self.input_ids = enc["input_ids"]
        self.attention_mask = enc["attention_mask"]
        self.labels = torch.tensor(scores, dtype=torch.float32)

    def __len__(self): return len(self.labels)

    def __getitem__(self, i):
        return self.input_ids[i], self.attention_mask[i], self.labels[i]


def build_dataset(tokenizer):
    texts, scores = [], []

    # Phase 2: EmoWOZ
    print("[Train-Phase2+3] Loading EmoWOZ...")
    try:
        emo = load_phase2_emowoz()
        for row in emo:
            utt = row.get("utterance") or row.get("text") or ""
            emotion = row.get("emotion", 0)
            if utt.strip():
                texts.append(utt)
                scores.append(emowoz_to_frustration(emotion))
        print(f"  → {len(texts)} EmoWOZ examples")
    except Exception as e:
        print(f"  [Warning] EmoWOZ load failed: {e}")

    # Phase 3: Bitext W-tagged
    print("[Train-Phase2+3] Loading Bitext...")
    try:
        bitext = load_phase3_bitext(frustrated_only=True)
        for row in bitext:
            utt = row.get("instruction") or ""
            if utt.strip():
                texts.append(utt)
                scores.append(0.80)   # W-tagged = high frustration signal
        print(f"  → Total with Bitext: {len(texts)}")
    except Exception as e:
        print(f"  [Warning] Bitext load failed: {e}")

    # Synthetic
    print("[Train-Phase2+3] Loading synthetic...")
    try:
        synth = load_synthetic()
        for ex in synth:
            texts.append(ex["text"])
            scores.append(float(ex["frustration_score"]))
        print(f"  → Total with synthetic: {len(texts)}")
    except Exception as e:
        print(f"  [Warning] Synthetic load failed: {e}")

    return TextFrustrationDataset(texts, scores, tokenizer)


def train():
    # Load base model (Phase 1 fine-tuned if available, else pretrained)
    phase1_path = os.path.join(os.path.dirname(__file__), "saved", "sentiment_model")
    base = phase1_path if os.path.exists(phase1_path) else SENTIMENT_MODEL
    print(f"[Train-Phase2+3] Base model: {base}")

    tokenizer = AutoTokenizer.from_pretrained(base)
    model = FrustrationRegressor(base).to(DEVICE)

    dataset = build_dataset(tokenizer)
    val_size = max(100, int(0.1 * len(dataset)))
    train_ds, val_ds = random_split(dataset, [len(dataset) - val_size, val_size])

    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)
    val_loader   = DataLoader(val_ds,   batch_size=BATCH_SIZE)

    optimizer = AdamW(model.parameters(), lr=LR, weight_decay=0.01)
    total_steps = len(train_loader) * EPOCHS
    scheduler = get_linear_schedule_with_warmup(
        optimizer, num_warmup_steps=total_steps // 10,
        num_training_steps=total_steps
    )
    loss_fn = nn.MSELoss()

    best_val_loss = float("inf")

    for epoch in range(1, EPOCHS + 1):
        # Training
        model.train()
        total_loss = 0
        for ids, mask, labels in train_loader:
            ids, mask, labels = ids.to(DEVICE), mask.to(DEVICE), labels.to(DEVICE)
            optimizer.zero_grad()
            preds = model(ids, mask)
            loss = loss_fn(preds, labels)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            total_loss += loss.item()

        avg_train = total_loss / len(train_loader)

        # Validation
        model.eval()
        val_loss, maes = 0, []
        with torch.no_grad():
            for ids, mask, labels in val_loader:
                ids, mask, labels = ids.to(DEVICE), mask.to(DEVICE), labels.to(DEVICE)
                preds = model(ids, mask)
                val_loss += loss_fn(preds, labels).item()
                maes.extend(torch.abs(preds - labels).cpu().tolist())

        avg_val  = val_loss / len(val_loader)
        avg_mae  = np.mean(maes)
        print(f"  Epoch {epoch}/{EPOCHS} | Train MSE: {avg_train:.4f} | Val MSE: {avg_val:.4f} | MAE: {avg_mae:.4f}")

        if avg_val < best_val_loss:
            best_val_loss = avg_val
            torch.save(model.state_dict(), os.path.join(SAVE_PATH, "best_model.pt"))
            tokenizer.save_pretrained(SAVE_PATH)
            print(f"  ✓ Best model saved (val_loss={best_val_loss:.4f})")

    # Save model config
    import json
    with open(os.path.join(SAVE_PATH, "training_config.json"), "w") as f:
        json.dump({"base_model": base, "epochs": EPOCHS, "batch_size": BATCH_SIZE,
                   "final_val_mse": best_val_loss}, f, indent=2)
    print(f"[Train-Phase2+3] Complete. Best val MSE: {best_val_loss:.4f}")


if __name__ == "__main__":
    train()


# Phase 2, 3, 4 — Frustration Regression Training
# All data comes from twcs.csv
#
# Phase 2 → high frustration examples   (score >= 0.65)
# Phase 3 → moderate frustration        (score 0.30 – 0.65)
# Phase 4 → full dataset                (all customer messages)
#
# Run: python models/train_frustration.py

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import torch
import numpy as np
import torch.nn as nn
from torch.optim import AdamW
from torch.utils.data import DataLoader, random_split
from transformers import AutoTokenizer, AutoModel, get_linear_schedule_with_warmup
from data.dataset_loader import (load_phase2_high_frustration,
                                  load_phase3_moderate_frustration,
                                  load_phase4_full, FrustrationDataset)
from config import SENTIMENT_MODEL, DEVICE

SAVE_PATH  = os.path.join(os.path.dirname(__file__), "saved", "frustration_model")
BATCH_SIZE = 16
LR         = 2e-5
os.makedirs(SAVE_PATH, exist_ok=True)


# ── Frustration Regressor Model ───────────────────────────────────────────────
class FrustrationRegressor(nn.Module):
    def __init__(self, base_model_path: str):
        super().__init__()
        self.encoder = AutoModel.from_pretrained(base_model_path)
        h = self.encoder.config.hidden_size
        self.head = nn.Sequential(
            nn.Dropout(0.1),
            nn.Linear(h, 128),
            nn.ReLU(),
            nn.Linear(128, 1),
            nn.Sigmoid()
        )

    def forward(self, input_ids, attention_mask):
        out = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        cls = out.last_hidden_state[:, 0, :]
        return self.head(cls).squeeze(-1)


def train_phase(model, tokenizer, examples, phase_name, epochs, save_best=True):
    """Train the model on a set of examples for N epochs."""
    print(f"\n{'='*60}")
    print(f"  {phase_name}  |  {len(examples):,} examples  |  {epochs} epochs")
    print(f"{'='*60}")

    texts  = [e["text"]               for e in examples]
    scores = [e["frustration_score"]  for e in examples]

    dataset  = FrustrationDataset(texts, scores, tokenizer)
    val_size = max(100, int(0.1 * len(dataset)))
    train_ds, val_ds = random_split(
        dataset, [len(dataset) - val_size, val_size],
        generator=torch.Generator().manual_seed(42)
    )

    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)
    val_loader   = DataLoader(val_ds,   batch_size=BATCH_SIZE)

    optimizer    = AdamW(model.parameters(), lr=LR, weight_decay=0.01)
    total_steps  = len(train_loader) * epochs
    scheduler    = get_linear_schedule_with_warmup(
        optimizer, num_warmup_steps=total_steps // 10,
        num_training_steps=total_steps
    )
    loss_fn  = nn.MSELoss()
    best_val = float("inf")

    for epoch in range(1, epochs + 1):
        # ── Train ─────────────────────────────────────────────────────────────
        model.train()
        t_loss = 0
        for batch in train_loader:
            ids   = batch["input_ids"].to(DEVICE)
            mask  = batch["attention_mask"].to(DEVICE)
            lbls  = batch["labels"].to(DEVICE)
            optimizer.zero_grad()
            preds = model(ids, mask)
            loss  = loss_fn(preds, lbls)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            t_loss += loss.item()

        # ── Validate ──────────────────────────────────────────────────────────
        model.eval()
        v_loss, maes = 0, []
        with torch.no_grad():
            for batch in val_loader:
                ids   = batch["input_ids"].to(DEVICE)
                mask  = batch["attention_mask"].to(DEVICE)
                lbls  = batch["labels"].to(DEVICE)
                preds = model(ids, mask)
                v_loss += loss_fn(preds, lbls).item()
                maes.extend(torch.abs(preds - lbls).cpu().tolist())

        avg_t = t_loss / len(train_loader)
        avg_v = v_loss / len(val_loader)
        avg_m = np.mean(maes)
        print(f"  Epoch {epoch}/{epochs} | Train MSE: {avg_t:.4f} | Val MSE: {avg_v:.4f} | MAE: {avg_m:.4f}")

        if save_best and avg_v < best_val:
            best_val = avg_v
            torch.save(model.state_dict(), os.path.join(SAVE_PATH, "best_model.pt"))
            print(f"    ✓ Best model saved (val MSE: {best_val:.4f})")

    return best_val


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"  Frustration Model Training  |  Device: {DEVICE}")
    print(f"  All data from twcs.csv")
    print(f"{'='*60}")

    # Use Phase 1 checkpoint if available, else base model
    base = os.path.join(os.path.dirname(__file__), "saved", "sentiment_model")
    base = base if os.path.exists(base) else SENTIMENT_MODEL
    print(f"\nBase model: {base}")

    tokenizer = AutoTokenizer.from_pretrained(base)
    model     = FrustrationRegressor(base).to(DEVICE)

    # ── Phase 2: High frustration ─────────────────────────────────────────────
    phase2 = load_phase2_high_frustration()
    train_phase(model, tokenizer, phase2,
                "Phase 2 — High Frustration (score >= 0.65)", epochs=3)

    # ── Phase 3: Moderate frustration ────────────────────────────────────────
    phase3 = load_phase3_moderate_frustration()
    train_phase(model, tokenizer, phase3,
                "Phase 3 — Moderate Frustration (0.30 – 0.65)", epochs=3)

    # ── Phase 4: Full dataset ─────────────────────────────────────────────────
    phase4 = load_phase4_full()
    best   = train_phase(model, tokenizer, phase4,
                         "Phase 4 — Full Dataset (all messages)", epochs=4)

    # Save final model and tokeniser
    torch.save(model.state_dict(), os.path.join(SAVE_PATH, "best_model.pt"))
    tokenizer.save_pretrained(SAVE_PATH)

    print(f"\n{'='*60}")
    print(f"✅ All phases complete")
    print(f"   Best Val MSE: {best:.4f}")
    print(f"   Saved to:     {SAVE_PATH}")
    print(f"{'='*60}")


